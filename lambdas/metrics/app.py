"""
Metrics Lambda - Records workflow telemetry and computes aggregation data.
Emits structured events for Grafana observability.
"""

import json
from datetime import datetime
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Record workflow metrics and compute aggregations.
    
    Expected event format:
    {
        "run_id": "abc-123",
        "workflow_name": "partner-ingestion-dev",
        "event_type": "workflow_completed",
        "event_data": {"status": "success", "files_processed": 3},
        "environment": "dev"
    }
    """
    run_id = event.get("run_id", "unknown")
    workflow_name = event.get("workflow_name", "unknown")
    event_type = event.get("event_type", "unknown")
    event_data = event.get("event_data", {})
    environment = event.get("environment", "dev")

    # Build structured metric record
    metric_record = {
        "run_id": run_id,
        "workflow_name": workflow_name,
        "event_type": event_type,
        "event_data": event_data,
        "environment": environment,
        "timestamp": datetime.utcnow().isoformat(),
        "metric_version": "1.0",
    }

    # Compute summary for Grafana consumption
    summary = {
        "total_runs": 1,
        "successful_runs": 1 if event_data.get("status") == "success" else 0,
        "failed_runs": 1 if event_data.get("status") == "failed" else 0,
        "files_processed": event_data.get("files_processed", 0),
        "files_invalid": event_data.get("files_invalid", 0),
    }

    return {
        "status": "ok",
        "metric_record": metric_record,
        "summary": summary,
        "environment": environment,
    }