"""
S3 Event Router Lambda - EventBridge-triggered handler for S3 object creation events.
Performs CSV validation and routes files to appropriate buckets:
  - Good/valid data  -> ingestion-good bucket
  - Bad/inconsistent -> ingestion-quarantine bucket
All pipeline events are logged to the audit S3 bucket for security & compliance.
No PostgreSQL dependency, no cron jobs - fully event-driven.
"""

import json
import os
import csv
import io
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------
STORAGE_ENDPOINT = os.getenv("STORAGE_ENDPOINT", "http://localhost:9000")
STORAGE_ACCESS_KEY = os.getenv("STORAGE_ACCESS_KEY", "minioadmin")
STORAGE_SECRET_KEY = os.getenv("STORAGE_SECRET_KEY", "minioadmin")

BUCKET_SOURCE = os.getenv("STORAGE_BUCKET_RAW", "ingestion-raw")
BUCKET_GOOD = os.getenv("STORAGE_BUCKET_GOOD", "ingestion-good")
BUCKET_QUARANTINE = os.getenv("STORAGE_BUCKET_QUARANTINE", "ingestion-quarantine")
BUCKET_AUDIT = os.getenv("STORAGE_BUCKET_AUDIT", "ingestion-audit")

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

REQUIRED_COLUMNS = ["partner_id", "date", "amount", "currency"]


# ---------------------------------------------------------------------------
# S3 Client
# ---------------------------------------------------------------------------
def _get_s3_client():
    """Get S3 client configured for local MinIO or AWS S3."""
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


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------
def _write_audit_log(
    s3_client,
    event_type: str,
    source: str,
    details: Dict[str, Any],
    severity: str = "INFO",
    log_id: str = None,
) -> Dict[str, Any]:
    """Write a structured audit log entry to the audit S3 bucket."""
    now = datetime.now(timezone.utc)
    log_id = log_id or f"{source}/{event_type}/{now.strftime('%Y/%m/%d/%H%M%S%f')}"

    log_entry = {
        "timestamp": now.isoformat(),
        "event_type": event_type,
        "source": source,
        "severity": severity,
        "details": details,
        "service": "floci-ingestion-pipeline",
        "environment": ENVIRONMENT,
    }
    log_content = json.dumps(log_entry, indent=2)
    log_key = f"audit-logs/{now.strftime('%Y/%m/%d')}/{log_id}.json"

    try:
        s3_client.put_object(
            Bucket=BUCKET_AUDIT,
            Key=log_key,
            Body=log_content.encode("utf-8"),
            ContentType="application/json",
        )
        return {"status": "logged", "log_key": log_key}
    except Exception as e:
        # Fallback: log to stdout if S3 write fails
        print(f"AUDIT_LOG_FALLBACK [{log_key}]: {log_content}")
        return {"status": "fallback_stdout", "log_key": log_key, "error": str(e)}


# ---------------------------------------------------------------------------
# CSV Validation
# ---------------------------------------------------------------------------
def _validate_csv(content: str, filename: str) -> Tuple[bool, List[str], int]:
    """
    Validate a CSV file against required columns and data quality rules.
    Returns (is_valid, list_of_errors, row_count).
    """
    errors: List[str] = []

    try:
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            return False, ["Empty or unreadable CSV - no headers found"], 0

        # Check required column headers
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            return False, [f"Missing required columns: {', '.join(missing)}"], 0

        # Validate each row
        row_count = 0
        for row_num, row in enumerate(reader, start=2):
            row_count += 1
            row_errors = _validate_row(row, row_num)
            errors.extend(row_errors)

        if row_count == 0:
            errors.append("CSV file has no data rows")

    except csv.Error as e:
        return False, [f"CSV parse error: {str(e)}"], 0
    except Exception as e:
        return False, [f"Unexpected validation error: {str(e)}"], 0

    return len(errors) == 0, errors, row_count


def _validate_row(row: Dict[str, str], row_num: int) -> List[str]:
    """Validate a single CSV row and return a list of errors."""
    errors: List[str] = []

    # partner_id: required, non-empty, numeric
    partner_id = row.get("partner_id", "").strip()
    if not partner_id:
        errors.append(f"Row {row_num}: Empty partner_id")
    elif not partner_id.isdigit():
        errors.append(f"Row {row_num}: partner_id '{partner_id}' is not numeric")

    # date: required, valid ISO format YYYY-MM-DD
    date_val = row.get("date", "").strip()
    if not date_val:
        errors.append(f"Row {row_num}: Empty date")
    else:
        try:
            datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Row {row_num}: date '{date_val}' not in YYYY-MM-DD format")

    # amount: required, positive number
    amount_val = row.get("amount", "").strip()
    if not amount_val:
        errors.append(f"Row {row_num}: Empty amount")
    else:
        try:
            amount = float(amount_val)
            if amount < 0:
                errors.append(f"Row {row_num}: Negative amount '{amount_val}'")
            elif amount == 0:
                errors.append(f"Row {row_num}: Zero amount '{amount_val}'")
        except ValueError:
            errors.append(f"Row {row_num}: amount '{amount_val}' is not a valid number")

    # currency: required, 3-letter ISO code
    currency = row.get("currency", "").strip()
    if not currency:
        errors.append(f"Row {row_num}: Empty currency")
    elif len(currency) != 3 or not currency.isalpha():
        errors.append(f"Row {row_num}: currency '{currency}' is not a valid 3-letter ISO code")

    return errors


# ---------------------------------------------------------------------------
# CSV Processing (enrichment for valid data)
# ---------------------------------------------------------------------------
def _process_csv(content: str, filename: str) -> Tuple[str, int]:
    """
    Enrich a valid CSV with processing metadata columns.
    Returns (processed_content, row_count).
    """
    reader = csv.DictReader(io.StringIO(content))
    output = io.StringIO()

    fieldnames = reader.fieldnames + [
        "processed_at",
        "processing_version",
        "environment",
        "source_file",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    now = datetime.now(timezone.utc).isoformat()
    row_count = 0

    for row in reader:
        row_count += 1
        row["processed_at"] = now
        row["processing_version"] = "1.0.0"
        row["environment"] = ENVIRONMENT
        row["source_file"] = filename
        # Normalize whitespace
        row = {k: v.strip() if isinstance(v, str) else v for k, v in row.items()}
        writer.writerow(row)

    return output.getvalue(), row_count


# ---------------------------------------------------------------------------
# Main Lambda Handler - Entry point triggered by EventBridge
# ---------------------------------------------------------------------------
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle S3 object creation events forwarded by EventBridge.

    Supports two event formats:
    1. AWS EventBridge S3 event notification format (detail-type: "Object Created")
    2. Direct invocation with {"file_key": "...", "content": "..."} for testing

    For each file:
      - Reads from source (ingestion-raw) bucket
      - Validates CSV structure & content
      - Routes to good data bucket (ingestion-good) if valid
      - Routes to quarantine bucket (ingestion-quarantine) if invalid
      - Logs everything to audit bucket (ingestion-audit)
    """
    s3 = _get_s3_client()
    results: Dict[str, Any] = {
        "processed_files": [],
        "total_files": 0,
        "good_count": 0,
        "quarantine_count": 0,
        "errors": [],
    }

    # -----------------------------------------------------------------------
    # Extract file(s) to process from the event
    # -----------------------------------------------------------------------
    files_to_process: List[Dict[str, str]] = []

    # Check if this is a direct invocation (for testing)
    if "file_key" in event and "content" in event:
        files_to_process.append({
            "file_key": event["file_key"],
            "content": event["content"],
        })
    elif "file_key" in event:
        # Has file_key but no content - fetch from S3
        files_to_process.append({"file_key": event["file_key"]})
    elif "detail" in event and "bucket" in event.get("detail", {}):
        # EventBridge S3 event notification format
        detail = event["detail"]
        bucket_name = detail.get("bucket", {}).get("name", BUCKET_SOURCE)
        object_key = unquote_plus(detail.get("object", {}).get("key", ""))
        if object_key:
            files_to_process.append({
                "file_key": object_key,
                "bucket": bucket_name,
            })
    elif "Records" in event:
        # S3 PUT event notification format (legacy)
        for record in event["Records"]:
            if record.get("eventSource") == "aws:s3":
                bucket_name = record.get("s3", {}).get("bucket", {}).get("name", BUCKET_SOURCE)
                object_key = unquote_plus(record.get("s3", {}).get("object", {}).get("key", ""))
                if object_key:
                    files_to_process.append({
                        "file_key": object_key,
                        "bucket": bucket_name,
                    })

    results["total_files"] = len(files_to_process)

    if not files_to_process:
        msg = "No files to process - no file_key found in event"
        _write_audit_log(s3, "no_files", "s3_event_router", {"event": str(event)[:500]}, "WARN")
        return {"status": "no_files", "message": msg}

    # -----------------------------------------------------------------------
    # Process each file
    # -----------------------------------------------------------------------
    for file_info in files_to_process:
        file_key = file_info["file_key"]
        source_bucket = file_info.get("bucket", BUCKET_SOURCE)
        file_result: Dict[str, Any] = {"file_key": file_key, "status": "unknown"}

        try:
            # --- Step 1: Read file content from S3 ---
            content: str = file_info.get("content", "")
            if not content:
                response = s3.get_object(Bucket=source_bucket, Key=file_key)
                content = response["Body"].read().decode("utf-8")

            _write_audit_log(
                s3, "file_read", "s3_event_router",
                {"file_key": file_key, "bucket": source_bucket, "size_bytes": len(content)},
            )

            # --- Step 2: Validate CSV ---
            is_valid, errors, row_count = _validate_csv(content, file_key)

            # --- Step 3: Route based on validation result ---
            if is_valid:
                # ---- Route to GOOD DATA bucket ----
                processed_content, processed_rows = _process_csv(content, file_key)
                good_key = f"good_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file_key}"

                s3.put_object(
                    Bucket=BUCKET_GOOD,
                    Key=good_key,
                    Body=processed_content.encode("utf-8"),
                )

                file_result["status"] = "good"
                file_result["routed_to"] = BUCKET_GOOD
                file_result["output_key"] = good_key
                file_result["row_count"] = processed_rows
                results["good_count"] += 1

                _write_audit_log(
                    s3, "file_routed_good", "s3_event_router",
                    {
                        "file_key": file_key,
                        "output_key": good_key,
                        "row_count": processed_rows,
                        "destination_bucket": BUCKET_GOOD,
                    },
                )

            else:
                # ---- Route to QUARANTINE bucket ----
                quarantine_key = f"quarantine_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file_key}"
                manifest = {
                    "original_file": file_key,
                    "source_bucket": source_bucket,
                    "quarantine_reason": "validation_failed",
                    "errors": errors,
                    "row_count": row_count,
                    "quarantined_at": datetime.now(timezone.utc).isoformat(),
                    "environment": ENVIRONMENT,
                }

                # Write the original content alongside a manifest
                combined = f"# QUARANTINE MANIFEST\n{json.dumps(manifest, indent=2)}\n# --- ORIGINAL FILE CONTENT ---\n{content}"
                s3.put_object(
                    Bucket=BUCKET_QUARANTINE,
                    Key=quarantine_key,
                    Body=combined.encode("utf-8"),
                )

                file_result["status"] = "quarantined"
                file_result["routed_to"] = BUCKET_QUARANTINE
                file_result["output_key"] = quarantine_key
                file_result["errors"] = errors
                results["quarantine_count"] += 1

                _write_audit_log(
                    s3, "file_routed_quarantine", "s3_event_router",
                    {
                        "file_key": file_key,
                        "output_key": quarantine_key,
                        "errors": errors,
                        "destination_bucket": BUCKET_QUARANTINE,
                    },
                    severity="WARN",
                )

            results["processed_files"].append(file_result)

        except ClientError as e:
            error_msg = f"S3 error processing {file_key}: {str(e)}"
            file_result["status"] = "error"
            file_result["error"] = error_msg
            results["errors"].append(error_msg)

            _write_audit_log(
                s3, "file_error", "s3_event_router",
                {"file_key": file_key, "error": error_msg},
                severity="ERROR",
            )

        except Exception as e:
            error_msg = f"Unexpected error processing {file_key}: {str(e)}"
            file_result["status"] = "error"
            file_result["error"] = error_msg
            results["errors"].append(error_msg)

            _write_audit_log(
                s3, "file_error", "s3_event_router",
                {"file_key": file_key, "error": error_msg},
                severity="ERROR",
            )

    # -----------------------------------------------------------------------
    # Summary audit log
    # -----------------------------------------------------------------------
    _write_audit_log(
        s3,
        "batch_completed",
        "s3_event_router",
        {
            "total_files": results["total_files"],
            "good_count": results["good_count"],
            "quarantine_count": results["quarantine_count"],
            "error_count": len(results["errors"]),
            "files": [f["file_key"] for f in results["processed_files"]],
        },
    )

    overall_status = "completed"
    if results["quarantine_count"] > 0 and results["good_count"] == 0:
        overall_status = "completed_all_quarantined"
    elif len(results["errors"]) > 0:
        overall_status = "completed_with_errors"

    return {
        "status": overall_status,
        "good_count": results["good_count"],
        "quarantine_count": results["quarantine_count"],
        "error_count": len(results["errors"]),
        "processed_files": results["processed_files"],
    }