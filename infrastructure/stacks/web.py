"""Frontend hosting: private S3 bucket behind CloudFront with Origin Access Control (D-009).

- The bucket is never public; only this CloudFront distribution can read it (OAC).
- HTTPS only, with security headers including a Content-Security-Policy.
- The React build is produced during synth (local `npm run build`, Docker fallback).
- Runtime settings (API URL, Cognito IDs) are written as /config.json at deploy
  time, so one build works for any deployment and no IDs are baked into source.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import aws_cdk as cdk
import jsii
from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@jsii.implements(cdk.ILocalBundling)
class _LocalViteBuild:
    def try_bundle(self, output_dir: str, _options: Any = None) -> bool:
        npm = shutil.which("npm")
        if npm is None:
            print("[clouddocs] npm not found, falling back to Docker build")
            return False
        try:
            if not (FRONTEND_DIR / "node_modules").exists():
                subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND_DIR, check=True)
            subprocess.run(
                [npm, "run", "build", "--", "--outDir", output_dir, "--emptyOutDir"],
                cwd=FRONTEND_DIR,
                check=True,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"[clouddocs] local frontend build failed, falling back to Docker: {exc}")
            return False
        return True


def frontend_source() -> s3deploy.ISource:
    return s3deploy.Source.asset(
        str(FRONTEND_DIR),
        exclude=["node_modules", "dist", ".env", ".env.*", "*.log"],
        bundling=cdk.BundlingOptions(
            image=cdk.DockerImage.from_registry("public.ecr.aws/docker/library/node:22"),
            local=_LocalViteBuild(),
            command=[
                "bash", "-c",
                "npm ci --no-audit --no-fund && npm run build -- --outDir /asset-output --emptyOutDir",
            ],
        ),
    )


def content_security_policy(region: str) -> str:
    # Wildcard API host avoids a CloudFront <-> API dependency cycle (the API's CORS
    # origin needs the CloudFront domain). Still limited to API Gateway in this Region.
    connect = " ".join(
        [
            "'self'",
            f"https://*.execute-api.{region}.amazonaws.com",
            f"https://cognito-idp.{region}.amazonaws.com",
        ]
    )
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",  # React/Amplify UI set inline style attributes
            "img-src 'self' data:",
            "font-src 'self' data:",
            f"connect-src {connect}",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


class Web(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, region: str) -> None:
        super().__init__(scope, construct_id)

        self.bucket = s3.Bucket(
            self,
            "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=RemovalPolicy.DESTROY,  # D-002
            auto_delete_objects=True,
        )

        headers = cloudfront.ResponseHeadersPolicy(
            self,
            "SecurityHeaders",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                content_security_policy=cloudfront.ResponseHeadersContentSecurityPolicy(
                    content_security_policy=content_security_policy(region), override=True
                ),
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.days(365), include_subdomains=True, override=True
                ),
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(override=True),
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.DENY, override=True
                ),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
                    override=True,
                ),
            ),
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment="CloudDocs AI frontend",
            default_root_object="index.html",
            price_class=cloudfront.PriceClass.PRICE_CLASS_200,  # includes Asia edge locations
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(self.bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=headers,
                compress=True,
            ),
            error_responses=[
                # Single-page app: unknown paths serve index.html.
                cloudfront.ErrorResponse(
                    http_status=403, response_http_status=200, response_page_path="/index.html", ttl=Duration.seconds(0)
                ),
                cloudfront.ErrorResponse(
                    http_status=404, response_http_status=200, response_page_path="/index.html", ttl=Duration.seconds(0)
                ),
            ],
        )

    @property
    def url(self) -> str:
        return f"https://{self.distribution.distribution_domain_name}"

    def deploy_site(self, runtime_config: dict[str, str]) -> None:
        """Upload the React build plus /config.json, then invalidate the CDN cache."""
        log_group = logs.LogGroup(
            self, "DeployLogs", retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY
        )
        s3deploy.BucketDeployment(
            self,
            "DeploySite",
            destination_bucket=self.bucket,
            sources=[frontend_source(), s3deploy.Source.json_data("config.json", runtime_config)],
            cache_control=[s3deploy.CacheControl.no_cache()],  # dev: always fresh after redeploy
            distribution=self.distribution,
            distribution_paths=["/*"],
            memory_limit=512,
            log_group=log_group,
        )
