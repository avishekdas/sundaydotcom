"""BlobStore port (files, imports/exports; arch 07 SEC-1): presigned POST with size/type limits, signed GET."""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Protocol
from urllib.parse import quote


class BlobStore(Protocol):
    def presign_post(
        self, key: str, *, max_bytes: int, content_type: str, expires_s: int
    ) -> dict[str, Any]: ...
    def presign_get(self, key: str, *, filename: str, expires_s: int) -> str: ...
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def head(self, key: str) -> int | None: ...
    def read_prefix(self, key: str, n: int) -> bytes: ...
    def delete(self, key: str) -> None: ...


def _disposition(filename: str) -> str:
    safe = re.sub(r'[\r\n"\\]', "_", filename)[:200] or "download"
    return f"attachment; filename=\"{safe}\"; filename*=UTF-8''{quote(filename[:200])}"


class S3BlobStore:
    def __init__(self, client: Any, bucket: str) -> None:
        self._s3, self._b = client, bucket

    def presign_post(self, key: str, *, max_bytes: int, content_type: str, expires_s: int) -> dict[str, Any]:
        res: dict[str, Any] = self._s3.generate_presigned_post(
            Bucket=self._b,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[["content-length-range", 1, max_bytes], {"Content-Type": content_type}],
            ExpiresIn=expires_s,
        )
        return res

    def presign_get(self, key: str, *, filename: str, expires_s: int) -> str:
        url: str = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._b, "Key": key, "ResponseContentDisposition": _disposition(filename)},
            ExpiresIn=expires_s,
        )
        return url

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(Bucket=self._b, Key=key, Body=data, ContentType=content_type)

    def head(self, key: str) -> int | None:
        try:
            return int(self._s3.head_object(Bucket=self._b, Key=key)["ContentLength"])
        except self._s3.exceptions.ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def read_prefix(self, key: str, n: int) -> bytes:
        body: bytes = self._s3.get_object(Bucket=self._b, Key=key, Range=f"bytes=0-{n - 1}")["Body"].read()
        return body

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._b, Key=key)


class InMemoryBlobStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def presign_post(self, key: str, *, max_bytes: int, content_type: str, expires_s: int) -> dict[str, Any]:
        policy = {
            "expiration": f"+{expires_s}s",
            "conditions": [
                ["content-length-range", 1, max_bytes],
                {"Content-Type": content_type},
                {"key": key},
            ],
        }
        return {
            "url": "memory://blobs",
            "fields": {
                "key": key,
                "Content-Type": content_type,
                "policy": base64.b64encode(json.dumps(policy).encode()).decode(),
            },
        }

    def presign_get(self, key: str, *, filename: str, expires_s: int) -> str:
        return f"memory://blobs/{quote(key)}?response-content-disposition={quote(_disposition(filename))}"

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def head(self, key: str) -> int | None:
        o = self.objects.get(key)
        return len(o[0]) if o else None

    def read_prefix(self, key: str, n: int) -> bytes:
        return self.objects[key][0][:n]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
