"""
FloCI EventBridge Simulator - Watches the raw S3 bucket for new files and
triggers the S3 Event Router Lambda via HTTP.

In production on AWS, EventBridge would natively detect S3:ObjectCreated:* events
and invoke the S3 Event Router Lambda directly. This script replicates that
behavior locally by polling the raw bucket for new objects.

Key behaviors:
  - No cron jobs required (no PostgreSQL scheduler)
  - Fully event-driven via S3 object creation polling
  - Tracks processed files to avoid re-processing
  - Forwards events to the S3 Event Router REST API
"""

import os
import time
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Set

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("eventbridge-simulator")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
STORAGE_ENDPOINT = os.getenv("STORAGE_ENDPOINT", "http://minio:9000")
STORAGE_ACCESS_KEY = os.getenv("STORAGE_ACCESS_KEY", "minioadmin")
STORAGE_SECRET_KEY = os.getenv("STORAGE_SECRET_KEY", "minioadmin")
BUCKET_RAW = os.getenv("STORAGE_BUCKET_RAW", "ingestion-raw")
ROUTER_API_URL = os.getenv("ROUTER_API_URL", "http://floci-s3-event-router:8081")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))


def _get_s3_client():
    """Get S3 client configured for local MinIO."""
    return boto3.client(
        "s3",
        endpoint_url=STORAGE_ENDPOINT,
        aws_access_key_id=STORAGE_ACCESS_KEY,
        aws_secret_access_key=STORAGE_SECRET_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 3},
        ),
    )


def _compute_file_hash(content: str) -> str:
    """Compute SHA-256 hash of file content for deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_known_files(state_file: str) -> Set[str]:
    """Load set of known file keys from a local state file."""
    try:
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                return set(json.load(f))
    except Exception as e:
        logger.warning(f"Could not load state file: {e}")
    return set()


def _save_known_files(state_file: str, known: Set[str]):
    """Save set of known file keys to a local state file."""
    try:
        with open(state_file, "w") as f:
            json.dump(list(known), f)
    except Exception as e:
        logger.warning(f"Could not save state file: {e}")


def _trigger_router(file_key: str, bucket: str, content: str = "") -> bool:
    """
    Trigger the S3 Event Router via HTTP (simulating EventBridge invocation).
    Returns True if triggered successfully.
    """
    try:
        payload = {
            "file_key": file_key,
            "content": content,
            "buckets": {
                "source": BUCKET_RAW,
            },
        }

        response = requests.post(
            f"{ROUTER_API_URL}/api/v1/process-event",
            json=payload,
            timeout=30,
        )

        if response.status_code == 200:
            result = response.json()
            status = result.get("status", "unknown")
            logger.info(
                f"Routed '{file_key}' -> "
                f"good={result.get('good_count', 0)}, "
                f"quarantine={result.get('quarantine_count', 0)}, "
                f"status={status}"
            )
            return True
        else:
            logger.error(
                f"Router returned {response.status_code} for '{file_key}': "
                f"{response.text[:200]}"
            )
            return False

    except requests.exceptions.ConnectionError:
        logger.warning(f"Router API not available yet, will retry '{file_key}' later")
        return False
    except Exception as e:
        logger.error(f"Failed to trigger router for '{file_key}': {e}")
        return False


def main():
    """Main loop: poll raw S3 bucket and trigger EventBridge-style events."""
    logger.info(
        f"EventBridge Simulator started: "
        f"watching '{BUCKET_RAW}' -> {ROUTER_API_URL} "
        f"(poll every {POLL_INTERVAL}s)"
    )

    s3 = _get_s3_client()
    state_file = "/tmp/eventbridge_processed_files.json"
    known_files: Set[str] = _get_known_files(state_file)

    logger.info(f"Known files (from state): {len(known_files)}")

    while True:
        try:
            # List objects in the raw bucket
            response = s3.list_objects_v2(Bucket=BUCKET_RAW)
            current_files: Set[str] = set()

            if "Contents" in response:
                for obj in response["Contents"]:
                    key = obj["Key"]
                    if key.endswith("/"):
                        continue
                    current_files.add(key)

            # Find new files that haven't been processed
            new_files = current_files - known_files

            if new_files:
                logger.info(f"Found {len(new_files)} new file(s): {', '.join(new_files)}")

            for file_key in sorted(new_files):
                logger.info(f"New object detected: {file_key} - triggering EventBridge event")

                # Read file content
                try:
                    obj_response = s3.get_object(Bucket=BUCKET_RAW, Key=file_key)
                    content = obj_response["Body"].read().decode("utf-8")
                except Exception as e:
                    logger.error(f"Could not read '{file_key}' from S3: {e}")
                    continue

                # Trigger the router
                success = _trigger_router(file_key, BUCKET_RAW, content)

                if success:
                    known_files.add(file_key)
                    _save_known_files(state_file, known_files)
                else:
                    # Don't add to known files - will retry on next poll
                    logger.info(f"Will retry '{file_key}' on next poll cycle")

            # Update known files list (in case files were deleted externally)
            known_files = current_files | known_files

            time.sleep(POLL_INTERVAL)

        except ClientError as e:
            logger.error(f"S3 error: {e}")
            time.sleep(POLL_INTERVAL * 2)
        except KeyboardInterrupt:
            logger.info("Shutting down EventBridge Simulator")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(POLL_INTERVAL * 2)


if __name__ == "__main__":
    main()