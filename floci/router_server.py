"""
FloCI S3 Event Router Server - FastAPI wrapper that emulates EventBridge invocation.
Listens for HTTP requests (simulating EventBridge events) and invokes the
S3 Event Router Lambda to validate and route CSV files.

This simulates how AWS EventBridge would trigger a Lambda when a new object
is created in the source S3 bucket, without needing actual AWS infrastructure.
"""

import os
import sys
import json
import logging
import boto3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import Counter

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Add lambdas to path so we can import the router
sys.path.insert(0, "/app")

from lambdas.s3_event_router.app import lambda_handler as s3_event_router_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FloCI S3 Event Router", version="1.0.0")


class EventBridgeEvent(BaseModel):
    """Simulated EventBridge event for S3 object creation."""
    file_key: str
    content: str = ""
    event_type: str = "Object Created"


class S3Notification(BaseModel):
    """Simulated S3 event notification."""
    bucket: str
    key: str


@app.get("/health")
async def health():
    return {"status": "ok", "service": "floci-s3-event-router"}


@app.get("/api/v1/metrics")
async def get_metrics():
    """
    Aggregate pipeline metrics from S3 audit logs for Grafana dashboards.
    Returns counts of good, quarantine, and error events with timestamps.
    """
    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("STORAGE_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.getenv("STORAGE_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("STORAGE_SECRET_KEY", "minioadmin"),
    )
    audit_bucket = os.getenv("STORAGE_BUCKET_AUDIT", "ingestion-audit")
    
    # List audit logs from last 24 hours
    prefix = f"audit-logs/{(datetime.utcnow() - timedelta(hours=24)).strftime('%Y/%m/%d')}"
    try:
        resp = s3.list_objects_v2(Bucket=audit_bucket, Prefix=prefix)
    except Exception:
        # No logs yet
        return {
            "total_events": 0,
            "good_files": 0,
            "quarantine_files": 0,
            "errors": 0,
            "events_by_type": [],
            "events_timeline": [],
        }
    
    logs = []
    for obj in resp.get("Contents", []):
        try:
            data = s3.get_object(Bucket=audit_bucket, Key=obj["Key"])
            log_entry = json.loads(data["Body"].read())
            logs.append(log_entry)
        except Exception:
            continue
    
    # Aggregate
    event_types = Counter(log.get("event_type") for log in logs)
    severities = Counter(log.get("severity") for log in logs)
    
    # Timeline: bucket by hour
    hourly = Counter()
    for log in logs:
        ts = log.get("timestamp", "")
        try:
            hour_key = ts[:13] + ":00:00"  # Group by hour
        except Exception:
            hour_key = "unknown"
        hourly[hour_key] += 1
    
    return {
        "total_events": len(logs),
        "good_files": event_types.get("file_routed_good", 0),
        "quarantine_files": event_types.get("file_routed_quarantine", 0),
        "errors": severities.get("ERROR", 0),
        "events_by_type": [{"event_type": k, "count": v} for k, v in event_types.items()],
        "events_timeline": [{"time": k, "count": v} for k, v in sorted(hourly.items())],
    }


@app.post("/api/v1/process-event")
async def process_event(event: EventBridgeEvent):
    """
    Simulates EventBridge triggering the Lambda when a new object is created in S3.
    
    Constructs an EventBridge-style event and invokes the S3 Event Router Lambda.
    """
    logger.info(f"Received EventBridge event for file: {event.file_key}")

    # Construct an EventBridge-style event payload
    eventbridge_payload = {
        "version": "0",
        "id": "local-eventbridge-simulator",
        "detail-type": event.event_type,
        "source": "aws.s3",
        "account": "123456789012",
        "time": __import__("datetime").datetime.utcnow().isoformat(),
        "region": "local",
        "resources": [f"arn:aws:s3:::{os.getenv('STORAGE_BUCKET_RAW', 'ingestion-raw')}"],
        "detail": {
            "version": "0",
            "bucket": {
                "name": os.getenv("STORAGE_BUCKET_RAW", "ingestion-raw"),
            },
            "object": {
                "key": event.file_key,
                "size": len(event.content) if event.content else 0,
                "etag": "local-simulator",
                "sequencer": "local-simulator",
            },
            "request-id": "local-simulator",
            "requester": "local-simulator",
            "source-ip-address": "127.0.0.1",
            "reason": "PutObject",
        },
    }

    # If content is provided, include it directly for efficiency
    if event.content:
        eventbridge_payload["file_key"] = event.file_key
        eventbridge_payload["content"] = event.content

    try:
        result = s3_event_router_handler(eventbridge_payload, {})
        return result
    except Exception as e:
        logger.error(f"Event processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/process-s3-event")
async def process_s3_event(notification: S3Notification):
    """
    Simulates an S3 event notification (via EventBridge).
    Fetches the file from MinIO/S3 and processes it.
    """
    logger.info(f"Received S3 notification for bucket={notification.bucket} key={notification.key}")

    eventbridge_payload = {
        "version": "0",
        "id": "local-eventbridge-s3",
        "detail-type": "Object Created",
        "source": "aws.s3",
        "detail": {
            "bucket": {"name": notification.bucket},
            "object": {"key": notification.key},
        },
    }

    try:
        result = s3_event_router_handler(eventbridge_payload, {})
        return result
    except Exception as e:
        logger.error(f"S3 event processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))