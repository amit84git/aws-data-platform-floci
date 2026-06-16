"""
FloCI Scheduler - Triggers workflow executions on a schedule.
Runs as a standalone service and submits workflow runs to the engine.
"""

import os
import time
import json
import logging
import requests
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

FLOCI_API_URL = os.getenv("FLOCI_API_URL", "http://localhost:8080")
SCHEDULE_INTERVAL = int(os.getenv("SCHEDULE_INTERVAL_SECONDS", "60"))

# For demo purposes, simulate different environments
ENVIRONMENTS = ["dev", "test", "prod"]


def trigger_workflow(environment: str) -> bool:
    """Trigger a workflow run for the given environment."""
    try:
        response = requests.post(
            f"{FLOCI_API_URL}/api/v1/workflows",
            json={
                "name": f"partner-ingestion-{environment}",
                "environment": environment,
                "source_file": "scheduled",
                "start_immediately": True,
            },
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Triggered workflow {data['run_id']} for {environment}")
            return True
        else:
            logger.error(f"Failed to trigger workflow for {environment}: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Connection error to FloCI engine: {e}")
        return False


def run_schedule():
    """Main scheduler loop."""
    logger.info(f"FloCI Scheduler started. API: {FLOCI_API_URL}, Interval: {SCHEDULE_INTERVAL}s")
    
    # Run once immediately for quick demo
    for env in ENVIRONMENTS:
        trigger_workflow(env)
    
    while True:
        time.sleep(SCHEDULE_INTERVAL)
        logger.info("Scheduler tick - triggering workflows")
        for env in ENVIRONMENTS:
            trigger_workflow(env)


if __name__ == "__main__":
    run_schedule()