"""
Quarantine Lambda - Isolates invalid files and records failure metadata.
Generates quarantine manifests for audit and replay purposes.
"""

import json
from datetime import datetime
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Quarantine an invalid file with full audit metadata.
    
    Expected event format:
    {
        "file_key": "invalid_file.csv",
        "content": "partner_id,date,amount\n1,2026-01-01,100",
        "errors": ["Missing required columns: currency"],
        "original_bucket": "ingestion-raw",
        "environment": "dev"
    }
    """
    file_key = event.get("file_key", "unknown")
    content = event.get("content", "")
    errors = event.get("errors", ["No errors provided"])
    original_bucket = event.get("original_bucket", "ingestion-raw")
    environment = event.get("environment", "dev")

    # Generate quarantine manifest
    manifest = {
        "original_file": file_key,
        "original_bucket": original_bucket,
        "quarantine_timestamp": datetime.utcnow().isoformat(),
        "quarantine_reason": errors,
        "environment": environment,
        "file_size_bytes": len(content),
        "replay_status": "available",  # Can be replayed after fix
    }

    # Structured quarantine record for the metrics pipeline
    quarantine_record = {
        "status": "quarantined",
        "file_key": file_key,
        "manifest": manifest,
        "quarantine_bucket": "ingestion-quarantine",
        "environment": environment,
    }

    return quarantine_record