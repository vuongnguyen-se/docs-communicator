"""S3 implementation of ObjectStorage (D-013).

Uploads use a presigned POST: a short-lived signed form whose policy S3 itself
enforces. The policy pins the exact object key (server-generated), the content
type and a size range, so a browser cannot upload elsewhere, a different type,
or a file larger than the limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from ..models import PresignedPost
from ..services.interfaces import ObjectInfo

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

HEADER_BYTES = 8  # enough for the "%PDF-" magic check
_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


class S3ObjectStorage:
    def __init__(self, client: S3Client, bucket: str) -> None:
        self._s3, self._bucket = client, bucket

    def create_presigned_post(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> PresignedPost:
        post = self._s3.generate_presigned_post(
            Bucket=self._bucket,
            Key=key,  # boto3 adds an exact-match {"key": key} condition
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=ttl_seconds,
        )
        return PresignedPost(url=post["url"], fields={k: str(v) for k, v in post["fields"].items()})

    def head(self, key: str) -> ObjectInfo | None:
        try:
            meta = self._s3.head_object(Bucket=self._bucket, Key=key)
            size = int(meta["ContentLength"])
            first = b""
            if size > 0:
                obj = self._s3.get_object(
                    Bucket=self._bucket, Key=key, Range=f"bytes=0-{HEADER_BYTES - 1}"
                )
                first = obj["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND:
                return None
            raise
        return ObjectInfo(size=size, first_bytes=first)

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)
