"""
Audit Logger Lambda - Writes all pipeline events to the audit S3 bucket.
Provides a complete audit trail for security, compliance, and debugging.
Every file validation, routing decision, and processing step is logged.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

AUDIT_BUCKET = os.getenv("STORAGE_BUCKET_AUDIT", "ingestion-audit")


def _get_s3_client():
    """Get S3 client configured for local MinIO or AWS S3."""
    endpoint = os.getenv("STORAGE_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("STORAGE_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("STORAGE_SECRET_KEY", "minioadmin")

    return boto3.client(
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


def _format_log_entry(
    event_type: str,
    source: str,
    details: Dict[str, Any],
    severity: str = "INFO",
) -> str:
    """Format a structured audit log entry."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "source": source,
        "severity": severity,
        "details": details,
        "service": "floci-ingestion-pipeline",
    }
    return json.dumps(entry, indent=2)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Record an audit log entry to the audit S3 bucket.

    Expected event format:
    {
        "event_type": "file_validated|file_routed|file_processed|file_quarantined|error",
        "source": "s3_event_router|validator|processor|quarantine",
        "details": { ... },
        "severity": "INFO|WARN|ERROR",  # optional, defaults to INFO
        "log_id": "optional-custom-log-id"  # optional
    }
    """
    event_type = event.get("event_type", "unknown")
    source = event.get("source", "unknown")
    details = event.get("details", {})
    severity = event.get("severity", "INFO")
    log_id = event.get("log_id", None)

    if not log_id:
        log_id = f"{source}/{event_type}/{datetime.now(timezone.utc).strftime('%Y/%m/%d/%H%M%S%f')}"

    try:
        s3 = _get_s3_client()
        log_content = _format_log_entry(event_type, source, details, severity)
        log_key = f"audit-logs/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{log_id}.json"

        s3.put_object(
            Bucket=AUDIT_BUCKET,
            Key=log_key,
            Body=log_content.encode("utf-8"),
            ContentType="application/json",
        )

        return {
            "status": "logged",
            "log_key": log_key,
            "event_type": event_type,
            "severity": severity,
        }

    except ClientError as e:
        error_msg = f"Failed to write audit log to S3: {str(e)}"
        # Fallback: print to stdout so it shows in container logs
        print(f"AUDIT_LOG_FALLBACK: {log_content}")
        return {
            "status": "error",
            "error": error_msg,
            "fallback": "logged_to_stdout",
            "event_type": event_type,
        }
    except Exception as e:
        error_msg = f"Unexpected audit logging error: {str(e)}"
        print(f"AUDIT_LOG_FALLBACK: {log_content}")
        return {
            "status": "error",
            "error": error_msg,
            "fallback": "logged_to_stdout",
            "event_type": event_type,
        }