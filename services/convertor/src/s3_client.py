import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, BinaryIO, Dict, List, Optional

from aiobotocore.session import AioBaseClient, get_session
from botocore.exceptions import ClientError

from .config import get_s3_settings
from .exceptions import PresignFailedError, UploadFailedError

settings = get_s3_settings()
PART_SIZE = 1024 * 1024 * 10


class S3Client:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        endpoint_url: str,
        region_name: str,
        bucket_names: List[str],
    ):
        self.bucket_names = bucket_names
        self.config: Dict[str, str] = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "endpoint_url": endpoint_url,
            "region_name": region_name,
        }
        self.session = get_session()

    @asynccontextmanager
    async def _get_client(self) -> AsyncGenerator[AioBaseClient, None]:
        """
        Async context manager to create and yield an S3 client.

        This method initializes an S3 client using the session and configuration
        provided in the class instance and ensures proper cleanup after usage.

        Yields:
            aiobotocore.client.AioBaseClient: An asynchronous S3 client instance.
        """
        async with self.session.create_client("s3", **self.config) as client:
            yield client

    async def upload_file(
        self, filename: str, file_obj: BinaryIO, bucket_name: Optional[str] = None
    ) -> None:
        """Upload one object, or raise.

        This used to log a ClientError and return as if nothing had
        happened, so a failed upload travelled all the way back to
        main.py as success and the video was announced ready while its
        media was never stored.
        """
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        elif bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")

        async with self._get_client() as client:
            upload_id = None
            try:
                resp = await client.create_multipart_upload(
                    Bucket=bucket_name, Key=filename
                )
                upload_id = resp["UploadId"]
                parts = []
                part_number = 1

                while True:
                    chunk = file_obj.read(PART_SIZE)
                    if not chunk:
                        break
                    part_resp = await client.upload_part(
                        Bucket=bucket_name,
                        Key=filename,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=chunk,
                    )
                    parts.append({"ETag": part_resp["ETag"], "PartNumber": part_number})
                    part_number += 1

                await client.complete_multipart_upload(
                    Bucket=bucket_name,
                    Key=filename,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
                logging.info(f"File {filename} uploaded to {bucket_name}")
            except (ClientError, OSError) as e:
                # Inside the client's own scope, on purpose: the abort used
                # to run after the context manager had closed the session,
                # so the cleanup failed too and left an orphaned multipart
                # upload -- which holds storage and does not appear in a
                # normal listing.
                if upload_id is not None:
                    try:
                        await client.abort_multipart_upload(
                            Bucket=bucket_name, Key=filename, UploadId=upload_id
                        )
                    except ClientError as abort_error:
                        logging.error(
                            "Could not abort multipart upload for %s: %s",
                            filename,
                            abort_error,
                        )
                logging.error(f"Error uploading file: {e}")
                raise UploadFailedError(filename, cause=e) from e

    async def upload_dir(
        self, dirname: str, directory: Path, bucket_name: Optional[str] = None
    ) -> None:
        """Upload every file under `directory`, or raise on the first failure.

        Errors are not caught here any more. A half-written rendition set
        is not something to report as done, and the caller decides what a
        failed upload means.
        """
        for p in sorted(Path(directory).rglob("*")):
            if not p.is_file():
                continue
            key = str(dirname / p.relative_to(directory))
            # with-block: the handles used to be left to the garbage
            # collector, one per segment.
            with p.open("rb") as handle:
                await self.upload_file(key, handle, bucket_name)

    async def list_keys(
        self, prefix: str, bucket_name: Optional[str] = None
    ) -> list[str]:
        """Every object key under `prefix`."""
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        elif bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")

        keys: list[str] = []
        async with self._get_client() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    async def download_prefix(
        self, prefix: str, directory: Path, bucket_name: Optional[str] = None
    ) -> int:
        """Fetch everything under `prefix` into `directory`, keeping the
        layout below the prefix.

        A rendition is a playlist plus its segments, and the playlist
        names the segments by relative path -- so they have to sit beside
        it on disk for ffmpeg to read them back.
        """
        keys = await self.list_keys(prefix, bucket_name)
        async with self._get_client() as client:
            for key in keys:
                target = directory / key[len(prefix) :].lstrip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                response = await client.get_object(Bucket=bucket_name, Key=key)
                async with response["Body"] as stream:
                    target.write_bytes(await stream.read())
        return len(keys)

    async def delete_file(
        self, object_name: str, bucket_name: Optional[str] = None
    ) -> None:
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        elif bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")
        try:
            async with self._get_client() as client:
                await client.delete_object(Bucket=bucket_name, Key=object_name)
                logging.info(f"File {object_name} deleted from {bucket_name}")
        except ClientError as e:
            logging.error(f"Error deleting file: {e}")

    async def generate_presigned_url(
        self,
        object_name: str,
        bucket_name: str,
        expiry: int = 300,
    ) -> str:
        try:
            async with self._get_client() as client:
                url = await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket_name, "Key": object_name},
                    ExpiresIn=expiry,
                )
                return url
        except (ClientError, OSError) as e:
            # Raised as one of ours so main.py recognises it and can report
            # the encode as failed rather than leaving it in "processing".
            raise PresignFailedError(object_name, cause=e) from e


_s3_client_instance: Optional[S3Client] = None


def get_s3_client() -> S3Client:
    """
    Lazy initialization of the S3 client.
    The client will only be created on the first call to this function.
    """
    settings = get_s3_settings()
    assert settings.MINIO_ROOT_USER is not None, "MINIO_ROOT_USER is not set"
    assert settings.MINIO_ROOT_PASSWORD is not None, "MINIO_ROOT_PASSWORD is not set"
    assert settings.MINIO_ENDPOINT_URL is not None, "MINIO_ENDPOINT_URL is not set"
    assert settings.MINIO_REGION_NAME is not None, "MINIO_REGION_NAME is not set"
    assert settings.BUCKET_NAMES is not None, "BUCKET_NAMES is not set"

    global _s3_client_instance
    if _s3_client_instance is None:
        _s3_client_instance = S3Client(
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            endpoint_url=settings.MINIO_ENDPOINT_URL,
            region_name=settings.MINIO_REGION_NAME,
            bucket_names=settings.BUCKET_NAMES,
        )
    return _s3_client_instance
