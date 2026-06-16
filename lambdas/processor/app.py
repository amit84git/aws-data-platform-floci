"""
Processing Lambda - Processes validated CSV files into enriched output.
Normalizes data, adds metadata, and produces a cleaned artifact.
"""

import json
import csv
import io
from datetime import datetime
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process a validated CSV file.
    
    Expected event format:
    {
        "file_key": "partner_file_20260101.csv",
        "content": "partner_id,date,amount,currency\n1,2026-01-01,100,USD",
        "environment": "dev"
    }
    """
    file_key = event.get("file_key", "unknown")
    content = event.get("content", "")
    environment = event.get("environment", "dev")

    if not content:
        return {
            "status": "error",
            "file_key": file_key,
            "error": "Empty file content",
            "environment": environment,
        }

    try:
        reader = csv.DictReader(io.StringIO(content))
        output = io.StringIO()

        # Add enrichment columns
        fieldnames = reader.fieldnames + [
            "processed_at",
            "processing_version",
            "environment",
            "source_file",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        now = datetime.utcnow().isoformat()
        row_count = 0

        for row in reader:
            row_count += 1
            # Enrich with processing metadata
            row["processed_at"] = now
            row["processing_version"] = "1.0.0"
            row["environment"] = environment
            row["source_file"] = file_key
            # Normalize: trim whitespace from all values
            row = {k: v.strip() if isinstance(v, str) else v for k, v in row.items()}
            writer.writerow(row)

        processed_content = output.getvalue()

        return {
            "status": "success",
            "file_key": file_key,
            "processed_content": processed_content,
            "row_count": row_count,
            "environment": environment,
            "output_format": "csv",
            "processing_version": "1.0.0",
        }

    except csv.Error as e:
        return {
            "status": "error",
            "file_key": file_key,
            "error": f"CSV processing error: {str(e)}",
            "environment": environment,
        }
    except Exception as e:
        return {
            "status": "error",
            "file_key": file_key,
            "error": f"Unexpected processing error: {str(e)}",
            "environment": environment,
        }