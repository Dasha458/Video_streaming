import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, BinaryIO, Dict, List, Optional

from aiobotocore.session import AioBaseClient, get_session
from botocore.exceptions import ClientError

from src.config import get_github_oauth_settings, get_s3_settings
from src.errors.files import (
    FileNotFoundS3Error,
    S3DeletionError,
    S3DownloadError,
    VideoUploadFailedError,
)

PART_SIZE = 1024 * 1024 * 10


class S3Client:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        endpoint_url: str,
        region_name: str,
        bucket_names: List[str],
        server_side_encryption: str | None = None,
    ):
        self.bucket_names = bucket_names
        self.config: Dict[str, str] = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "endpoint_url": endpoint_url,
            "region_name": region_name,
        }
        self.server_side_encryption = server_side_encryption
        self.session = get_session()

    async def check_bucket_exists(self) -> None:

        async with self._get_client() as client:
            for bucket_name in self.bucket_names:
                try:
                    await client.head_bucket(Bucket=bucket_name)
                    logging.info(f"Bucket '{bucket_name}' already exists")
                except ClientError:
                    await client.create_bucket(Bucket=bucket_name)
                    await client.put_bucket_versioning(
                        Bucket=bucket_name,
                        VersioningConfiguration={"Status": "Enabled"},
                    )
                    try:
                        await client.put_bucket_cors(
                            Bucket=bucket_name,
                            CORSConfiguration={
                                "CORSRules": [
                                    {
                                        "AllowedHeaders": ["Authorization", "Range"],
                                        "AllowedMethods": ["GET"],
                                        "AllowedOrigins": [
                                            get_github_oauth_settings().FRONTEND_URL
                                        ],
                                        "ExposeHeaders": ["ETag"],
                                        "MaxAgeSeconds": 3000,
                                    }
                                ]
                            },
                        )
                    except ClientError as e:
                        logging.warning(f"Could not set CORS for '{bucket_name}': {e}")
                    logging.info(f"Bucket '{bucket_name}' created")

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
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        elif bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")

        async with self._get_client() as client:
            upload_id = None
            try:
                resp = await client.create_multipart_upload(
                    Bucket=bucket_name,
                    Key=filename,
                    # ServerSideEncryption=self.server_side_encryption
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
                # Inside the client's scope on purpose: the abort used to run
                # after the context manager had closed the session, so the
                # cleanup failed too and left an orphaned multipart upload --
                # which holds storage and does not show up in a listing.
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
                # Raised, not logged and forgotten. A swallowed failure here
                # told the caller the upload had worked: the video row was
                # committed, an encode job was queued for an object that was
                # never stored, and a thumbnail path was recorded pointing at
                # nothing.
                raise VideoUploadFailedError() from e

    # ── Multipart driven by the client ────────────────────────────────
    # upload_file above runs a multipart upload of its own, from a file
    # the server already holds in full. These are the same operation with
    # the parts arriving one HTTP request at a time, so a dropped
    # connection costs one part rather than the whole upload -- and no
    # single request is ever larger than a part.

    async def begin_multipart(self, key: str, bucket_name: str) -> str:
        """Start an upload and return the id the parts belong to."""
        self._check_bucket(bucket_name)
        async with self._get_client() as client:
            response = await client.create_multipart_upload(Bucket=bucket_name, Key=key)
            return str(response["UploadId"])

    async def upload_part(
        self, key: str, bucket_name: str, upload_id: str, part_number: int, body: bytes
    ) -> str:
        """Store one part and return its ETag, which completion needs."""
        self._check_bucket(bucket_name)
        async with self._get_client() as client:
            response = await client.upload_part(
                Bucket=bucket_name,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=body,
            )
            return str(response["ETag"])

    async def list_parts(
        self, key: str, bucket_name: str, upload_id: str
    ) -> list[dict]:
        """The parts storage holds, so a resumed upload can skip them.

        Asked of storage rather than remembered in the database: storage
        is the thing that decides whether a part exists, and a session
        row that disagreed with it would resume into a corrupt file.
        """
        self._check_bucket(bucket_name)
        parts: list[dict] = []
        async with self._get_client() as client:
            paginator = client.get_paginator("list_parts")
            async for page in paginator.paginate(
                Bucket=bucket_name, Key=key, UploadId=upload_id
            ):
                for part in page.get("Parts", []):
                    parts.append(
                        {
                            "PartNumber": part["PartNumber"],
                            "ETag": part["ETag"],
                            "Size": part.get("Size", 0),
                        }
                    )
        return sorted(parts, key=lambda p: p["PartNumber"])

    async def complete_multipart(
        self, key: str, bucket_name: str, upload_id: str, parts: list[dict]
    ) -> None:
        """Assemble the parts into the object."""
        self._check_bucket(bucket_name)
        async with self._get_client() as client:
            await client.complete_multipart_upload(
                Bucket=bucket_name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={
                    "Parts": [
                        {"PartNumber": p["PartNumber"], "ETag": p["ETag"]}
                        for p in parts
                    ]
                },
            )

    async def abort_multipart(self, key: str, bucket_name: str, upload_id: str) -> None:
        """Discard an unfinished upload.

        Worth doing explicitly: an abandoned multipart upload holds the
        parts already sent and appears in no object listing, so the space
        is spent and invisible.
        """
        self._check_bucket(bucket_name)
        try:
            async with self._get_client() as client:
                await client.abort_multipart_upload(
                    Bucket=bucket_name, Key=key, UploadId=upload_id
                )
        except ClientError as e:
            logging.warning("Could not abort upload %s for %s: %s", upload_id, key, e)

    async def iter_object(
        self, key: str, bucket_name: str, chunk_size: int = 1024 * 1024
    ) -> AsyncGenerator[bytes, None]:
        """Read an object back in pieces.

        Completion hashes the assembled file this way. The hash has to be
        computed by the server: it decides whether the upload is a
        duplicate, so a client-supplied one would be a client deciding.
        """
        self._check_bucket(bucket_name)
        async with self._get_client() as client:
            response = await client.get_object(Bucket=bucket_name, Key=key)
            async with response["Body"] as stream:
                # Through the underlying aiohttp stream: in this version
                # the body is a ClientResponse, whose read() takes no
                # size. Reading it whole would pull a 500 MB object into
                # memory just to hash it.
                async for chunk in stream.content.iter_chunked(chunk_size):
                    if chunk:
                        yield chunk

    async def delete_all_versions(self, key: str, bucket_name: str) -> int:
        """Remove an object and every version of it.

        Versioning is on for these buckets, so an ordinary delete only
        writes a delete marker: the object disappears from listings while
        its bytes stay as a noncurrent version. That is fine for a video
        somebody deleted -- the orphan sweeper collects those -- but a
        failed upload happens on an ordinary code path, several times a
        day, and each one would quietly keep a copy of the file.
        """
        self._check_bucket(bucket_name)
        removed = 0
        async with self._get_client() as client:
            paginator = client.get_paginator("list_object_versions")
            async for page in paginator.paginate(Bucket=bucket_name, Prefix=key):
                targets = [
                    {"Key": obj["Key"], "VersionId": obj["VersionId"]}
                    for kind in ("Versions", "DeleteMarkers")
                    for obj in page.get(kind, [])
                    # Prefix matching would also catch <key>-something.
                    if obj["Key"] == key
                ]
                if targets:
                    await client.delete_objects(
                        Bucket=bucket_name, Delete={"Objects": targets}
                    )
                    removed += len(targets)
        return removed

    def _check_bucket(self, bucket_name: str) -> None:
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        if bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")

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
            # delete_video wraps its deletions in a rollback that could never
            # run while this was swallowed.
            raise S3DeletionError() from e

    async def list_keys(
        self, prefix: str, bucket_name: Optional[str] = None
    ) -> list[str]:
        """Every object key under `prefix`.

        Deletion needs this because the original upload keeps whatever
        extension it arrived with, so its key cannot be derived from the
        video id alone.
        """
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        elif bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")

        keys: list[str] = []
        try:
            async with self._get_client() as client:
                paginator = client.get_paginator("list_objects_v2")
                async for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                    keys.extend(o["Key"] for o in page.get("Contents", []))
        except ClientError as e:
            logging.error(f"Error listing '{prefix}' in '{bucket_name}': {e}")
            raise S3DeletionError() from e
        return keys

    async def delete_prefix(
        self, prefix: str, bucket_name: Optional[str] = None
    ) -> None:
        """
        Deletes all objects under a given prefix (folder) in an S3 bucket.

        Example:
            await s3_client.delete_prefix("1234abcd/", bucket_name="videos")

        :param prefix: The folder or prefix path (e.g., 'folder/subfolder/').
        :param bucket_name: The name of the bucket to delete from.
        """
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        elif bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")
        if not prefix or prefix.strip() == "":
            raise ValueError(
                "Prefix cannot be empty — refusing to delete entire bucket"
            )

        try:
            async with self._get_client() as client:
                paginator = client.get_paginator("list_objects_v2")

                async for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                    objects = page.get("Contents", [])
                    if not objects:
                        logging.info(
                            f"No objects found under prefix '{prefix}' in '{bucket_name}'."
                        )
                        continue

                    delete_batch = {
                        "Objects": [{"Key": obj["Key"]} for obj in objects],
                        "Quiet": True,
                    }

                    if len(objects) > 1000:
                        for i in range(0, len(objects), 1000):
                            batch = objects[i : i + 1000]
                            await client.delete_objects(
                                Bucket=bucket_name,
                                Delete={
                                    "Objects": [{"Key": o["Key"]} for o in batch],
                                    "Quiet": True,
                                },
                            )
                    else:
                        await client.delete_objects(
                            Bucket=bucket_name, Delete=delete_batch
                        )

                    logging.info(
                        f"Deleted {len(objects)} objects under prefix '{prefix}' from '{bucket_name}'"
                    )

        except ClientError as e:
            logging.error(
                f"Error deleting prefix '{prefix}' from bucket '{bucket_name}': {e}"
            )
            raise

    async def list_objects(self, bucket_name: str) -> list[str]:
        """
        Lists objects in a bucket.
        :param bucket_name: The name of the bucket.
        :return: The list of objects in the bucket.
        """
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        elif bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")

        try:
            async with self._get_client() as client:
                response = await client.list_objects_v2(Bucket=bucket_name)
                return response.get("Contents", [])
        except ClientError as client_error:
            logging.error(
                "Couldn't list objects in bucket %s. Here's why: %s",
                bucket_name,
                client_error.response["Error"]["Message"],
            )
            raise

    async def get_bucket_list(self) -> List[str]:
        async with self._get_client() as client:
            response = await client.list_buckets()
            return [b["Name"] for b in response.get("Buckets", [])]

    async def download_file(
        self, object_name: str, chunk_size: int, bucket_name: Optional[str] = None
    ) -> AsyncGenerator[bytes, None]:
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        elif bucket_name not in self.bucket_names:
            raise ValueError("bucket_name is not in bucket_names")

        try:
            async with self._get_client() as client:
                head = await client.head_object(Bucket=bucket_name, Key=object_name)
                size = head["ContentLength"]

                for start in range(0, size, chunk_size):
                    end = min(start + chunk_size - 1, size - 1)
                    resp = await client.get_object(
                        Bucket=bucket_name,
                        Key=object_name,
                        Range=f"bytes={start}-{end}",
                    )
                    async with resp["Body"] as stream:
                        while True:
                            chunk = await stream.content.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk
                logging.info(
                    f"File {object_name} downloaded with chunk size {chunk_size}"
                )
        except ClientError as e:
            logging.error(f"Error downloading file: {e}")
            # Swallowing this ended the generator quietly, so the caller
            # streamed an empty 200 back to the browser instead of saying
            # the object is not there.
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundS3Error() from e
            raise S3DownloadError(object_name) from e

    async def generate_presigned_url(
        self,
        object_key: str,
        client_method: str,
        expires_in: int = 100,
        bucket_name: Optional[str] = None,
    ) -> str | None:
        if not bucket_name:
            raise ValueError("bucket_name must be provided")

        try:
            async with self._get_client() as client:
                url = await client.generate_presigned_url(
                    ClientMethod=client_method,
                    Params={"Bucket": bucket_name, "Key": object_key},
                    ExpiresIn=expires_in,
                )
                logging.info(f"Presigned URL generated for file '{object_key}'.")
                return url
        except ClientError:
            logging.error(
                f"Couldn't get a presigned URL for client method '{client_method}'."
            )
            return None


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
