"""
Storage client for S3-compatible object storage (MinIO).
Abstracts file operations for the ingestion workflow.
"""

import os
import io
from typing import List, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class StorageClient:
    """Client for S3-compatible storage operations."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str):
        self.endpoint = endpoint
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=10,
                retries={"max_attempts": 3},
            ),
        )

    async def ensure_buckets(self):
        """Ensure required buckets exist, creating them if needed."""
        buckets = [
            "ingestion-raw",
            "ingestion-valid",
            "ingestion-quarantine",
            "ingestion-processed",
            "ingestion-metrics",
        ]
        for bucket in buckets:
            try:
                self.client.head_bucket(Bucket=bucket)
            except ClientError:
                try:
                    self.client.create_bucket(Bucket=bucket)
                except ClientError as e:
                    print(f"Warning: Could not create bucket {bucket}: {e}")

    async def list_files(self, bucket: str, prefix: str = "") -> List[str]:
        """List files in a bucket with optional prefix."""
        try:
            response = self.client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            if "Contents" not in response:
                return []
            return [obj["Key"] for obj in response["Contents"] if not obj["Key"].endswith("/")]
        except ClientError as e:
            print(f"Error listing files in {bucket}: {e}")
            return []

    async def get_file(self, bucket: str, key: str) -> str:
        """Get file contents as string."""
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read().decode("utf-8")
        except ClientError as e:
            raise Exception(f"Error reading file {bucket}/{key}: {e}")

    async def put_file(self, bucket: str, key: str, content: str):
        """Write string content to a file."""
        try:
            self.client.put_object(
                Bucket=bucket,
                Key=key,
                Body=content.encode("utf-8"),
            )
        except ClientError as e:
            raise Exception(f"Error writing file {bucket}/{key}: {e}")

    async def copy_file(self, source_bucket: str, source_key: str,
                        dest_bucket: str, dest_key: str):
        """Copy a file between buckets."""
        try:
            copy_source = {"Bucket": source_bucket, "Key": source_key}
            self.client.copy_object(
                CopySource=copy_source,
                Bucket=dest_bucket,
                Key=dest_key,
            )
        except ClientError as e:
            raise Exception(f"Error copying {source_bucket}/{source_key}: {e}")

    async def delete_file(self, bucket: str, key: str):
        """Delete a file."""
        try:
            self.client.delete_object(Bucket=bucket, Key=key)
        except ClientError as e:
            raise Exception(f"Error deleting {bucket}/{key}: {e}")

    async def file_exists(self, bucket: str, key: str) -> bool:
        """Check if a file exists."""
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False