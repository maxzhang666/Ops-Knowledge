import asyncio
import io
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.runtime_config import resolve


class MinIOService:
    def __init__(self, runtime_cfg: dict | None = None):
        cfg = runtime_cfg or {}
        endpoint = resolve(cfg, "minio", "endpoint", settings.MINIO_ENDPOINT)
        access_key = resolve(cfg, "minio", "access_key", settings.MINIO_ACCESS_KEY)
        secret_key = resolve(cfg, "minio", "secret_key", settings.MINIO_SECRET_KEY)
        secure = resolve(cfg, "minio", "secure", settings.MINIO_SECURE)
        self.bucket = resolve(cfg, "minio", "bucket", settings.MINIO_BUCKET)

        self.client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if secure else 'http'}://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

    async def _run_sync(self, fn, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def ensure_bucket(self) -> None:
        try:
            await self._run_sync(self.client.head_bucket, Bucket=self.bucket)
        except ClientError:
            await self._run_sync(self.client.create_bucket, Bucket=self.bucket)

    async def upload(
        self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream"
    ) -> str:
        if isinstance(data, bytes):
            data = io.BytesIO(data)
        await self.ensure_bucket()
        await self._run_sync(
            self.client.upload_fileobj, data, self.bucket, key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    async def download(self, key: str) -> bytes:
        response = await self._run_sync(self.client.get_object, Bucket=self.bucket, Key=key)
        return response["Body"].read()

    async def delete(self, key: str) -> None:
        await self._run_sync(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> int:
        def _delete_all():
            paginator = self.client.get_paginator("list_objects_v2")
            count = 0
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                objects = page.get("Contents", [])
                if objects:
                    self.client.delete_objects(
                        Bucket=self.bucket,
                        Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
                    )
                    count += len(objects)
            return count

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _delete_all)

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )
