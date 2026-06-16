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
from typing import Dict, Any

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