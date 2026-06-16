"""
Validation Lambda - Validates CSV file structure and content.
Checks required columns, data types, and business rules.
"""

import json
import csv
import io
from typing import Dict, Any, List, Tuple


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Validate a CSV file before downstream processing.
    
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
            "valid": False,
            "file_key": file_key,
            "errors": ["Empty file content"],
            "environment": environment,
        }

    required_columns = ["partner_id", "date", "amount", "currency"]
    errors = []

    try:
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            return {
                "valid": False,
                "file_key": file_key,
                "errors": ["Empty or unreadable CSV - no headers found"],
                "environment": environment,
            }

        # Check column headers
        missing_columns = [c for c in required_columns if c not in reader.fieldnames]
        if missing_columns:
            return {
                "valid": False,
                "file_key": file_key,
                "errors": [f"Missing required columns: {', '.join(missing_columns)}"],
                "environment": environment,
            }

        # Validate each row
        row_count = 0
        for row_num, row in enumerate(reader, start=2):
            row_count += 1
            row_errors = _validate_row(row, row_num)
            errors.extend(row_errors)

        if row_count == 0:
            errors.append("CSV file has no data rows")

    except csv.Error as e:
        return {
            "valid": False,
            "file_key": file_key,
            "errors": [f"CSV parse error: {str(e)}"],
            "environment": environment,
        }
    except Exception as e:
        return {
            "valid": False,
            "file_key": file_key,
            "errors": [f"Unexpected validation error: {str(e)}"],
            "environment": environment,
        }

    return {
        "valid": len(errors) == 0,
        "file_key": file_key,
        "errors": errors,
        "row_count": row_count,
        "environment": environment,
    }


def _validate_row(row: Dict[str, str], row_num: int) -> List[str]:
    """Validate a single CSV row."""
    errors = []

    # partner_id: required, must be non-empty
    partner_id = row.get("partner_id", "").strip()
    if not partner_id:
        errors.append(f"Row {row_num}: Empty partner_id")
    elif not partner_id.isdigit():
        errors.append(f"Row {row_num}: partner_id '{partner_id}' is not a numeric value")

    # date: required, must be valid ISO date
    date_val = row.get("date", "").strip()
    if not date_val:
        errors.append(f"Row {row_num}: Empty date")
    else:
        from datetime import datetime
        try:
            datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Row {row_num}: date '{date_val}' is not in YYYY-MM-DD format")

    # amount: required, must be positive number
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

    # currency: required, must be 3-letter ISO code
    currency = row.get("currency", "").strip()
    if not currency:
        errors.append(f"Row {row_num}: Empty currency")
    elif len(currency) != 3 or not currency.isalpha():
        errors.append(f"Row {row_num}: currency '{currency}' is not a valid 3-letter ISO code")

    return errors