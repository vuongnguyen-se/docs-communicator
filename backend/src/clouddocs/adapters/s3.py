"""S3 adapter: presigned POST (with size/type policy), HEAD + header sniff, delete."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from ..models import PresignedPost
from ..services.interfaces import ObjectInfo
from .errors import aws_error_code, call

_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


class S3Storage:
    def __init__(self, client: Any, bucket: str) -> None:
        self._c, self._bucket = client, bucket

    def create_presigned_post(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> PresignedPost:
        # Policy conditions make S3 itself reject wrong type / oversize / empty uploads.
        resp = call(
            self._c.generate_presigned_post,
            Bucket=self._bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=ttl_seconds,
        )
        return PresignedPost(url=resp["url"], fields=dict(resp["fields"]))

    def head(self, key: str) -> ObjectInfo | None:
        try:
            meta = call(self._c.head_object, Bucket=self._bucket, Key=key)
            body = call(self._c.get_object, Bucket=self._bucket, Key=key, Range="bytes=0-7")
            first = body["Body"].read()
        except ClientError as exc:
            if aws_error_code(exc) in _NOT_FOUND:
                return None
            raise
        return ObjectInfo(size=int(meta["ContentLength"]), first_bytes=first)

    def delete(self, key: str) -> None:
        call(self._c.delete_object, Bucket=self._bucket, Key=key)
