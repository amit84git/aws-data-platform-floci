"""
FloCI Engine - Lightweight Workflow Orchestrator
=================================================
REST API for workflow execution, state tracking, and metrics.
Replaces Airflow for local-first execution while maintaining
workflow semantics (DAGs, retries, state persistence).
"""

import os
import json
import uuid
import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
from botocore.config import Config

from .models import (
    WorkflowRun, WorkflowCreate, WorkflowRunResponse,
    WorkflowEvent, MetricsRecord
)
from .db import init_db, get_session, WorkflowRunDB, MetricsDB
from .storage import StorageClient

app = FastAPI(title="FloCI Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize on startup
storage_client = None

@app.on_event("startup")
async def startup():
    global storage_client
    init_db()
    storage_client = StorageClient(
        endpoint=os.getenv("STORAGE_ENDPOINT", "http://localhost:9000"),
        access_key=os.getenv("STORAGE_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("STORAGE_SECRET_KEY", "minioadmin"),
    )
    # Ensure buckets exist
    await storage_client.ensure_buckets()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "floci-engine"}

@app.post("/api/v1/workflows", response_model=WorkflowRunResponse)
async def create_workflow(workflow: WorkflowCreate, background_tasks: BackgroundTasks):
    """Create and optionally start a workflow execution."""
    run_id = str(uuid.uuid4())
    session = get_session()
    try:
        db_run = WorkflowRunDB(
            run_id=run_id,
            workflow_name=workflow.name,
            environment=workflow.environment,
            source_file=workflow.source_file,
            status="created",
            created_at=datetime.datetime.utcnow()
        )
        session.add(db_run)
        session.commit()
    finally:
        session.close()

    if workflow.start_immediately:
        background_tasks.add_task(execute_workflow, run_id)

    return WorkflowRunResponse(
        run_id=run_id,
        workflow_name=workflow.name,
        status="created",
        environment=workflow.environment
    )

@app.get("/api/v1/workflows", response_model=List[WorkflowRunResponse])
async def list_workflows(
    status: Optional[str] = None,
    environment: Optional[str] = None,
    limit: int = 50
):
    """List workflow runs with optional filters."""
    session = get_session()
    try:
        query = session.query(WorkflowRunDB)
        if status:
            query = query.filter(WorkflowRunDB.status == status)
        if environment:
            query = query.filter(WorkflowRunDB.environment == environment)
        runs = query.order_by(WorkflowRunDB.created_at.desc()).limit(limit).all()
        return [
            WorkflowRunResponse(
                run_id=r.run_id,
                workflow_name=r.workflow_name,
                status=r.status,
                environment=r.environment,
                error_message=r.error_message
            ) for r in runs
        ]
    finally:
        session.close()

@app.get("/api/v1/workflows/{run_id}", response_model=WorkflowRunResponse)
async def get_workflow(run_id: str):
    """Get detailed workflow run information."""
    session = get_session()
    try:
        run = session.query(WorkflowRunDB).filter(WorkflowRunDB.run_id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        return WorkflowRunResponse(
            run_id=run.run_id,
            workflow_name=run.workflow_name,
            status=run.status,
            environment=run.environment,
            source_file=run.source_file,
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at
        )
    finally:
        session.close()

@app.post("/api/v1/workflows/{run_id}/retry")
async def retry_workflow(run_id: str, background_tasks: BackgroundTasks):
    """Retry a failed workflow run."""
    session = get_session()
    try:
        run = session.query(WorkflowRunDB).filter(WorkflowRunDB.run_id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        if run.status != "failed":
            raise HTTPException(status_code=400, detail="Only failed workflows can be retried")
        
        run.status = "retrying"
        run.error_message = None
        session.commit()
    finally:
        session.close()
    
    background_tasks.add_task(execute_workflow, run_id)
    return {"status": "retrying", "run_id": run_id}

@app.post("/api/v1/metrics")
async def record_metrics(metrics: MetricsRecord):
    """Record workflow metrics."""
    session = get_session()
    try:
        db_metrics = MetricsDB(
            run_id=metrics.run_id,
            workflow_name=metrics.workflow_name,
            event_type=metrics.event_type,
            event_data=json.dumps(metrics.event_data),
            environment=metrics.environment,
            created_at=datetime.datetime.utcnow()
        )
        session.add(db_metrics)
        session.commit()
    finally:
        session.close()
    return {"status": "recorded"}

@app.get("/api/v1/metrics/summary")
async def get_metrics_summary(environment: Optional[str] = None, hours: int = 24):
    """Get aggregated metrics summary."""
    session = get_session()
    try:
        since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
        query = session.query(MetricsDB).filter(MetricsDB.created_at >= since)
        if environment:
            query = query.filter(MetricsDB.environment == environment)
        
        records = query.all()
        summary = {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "invalid_files": 0,
            "processed_files": 0,
            "quarantined_files": 0,
            "total_duration_ms": 0
        }
        
        for r in records:
            data = json.loads(r.event_data) if isinstance(r.event_data, str) else r.event_data
            if r.event_type == "workflow_completed":
                summary["total_runs"] += 1
                if data.get("status") == "success":
                    summary["successful_runs"] += 1
                elif data.get("status") == "failed":
                    summary["failed_runs"] += 1
            elif r.event_type == "file_invalid":
                summary["invalid_files"] += 1
            elif r.event_type == "file_processed":
                summary["processed_files"] += 1
            elif r.event_type == "file_quarantined":
                summary["quarantined_files"] += 1
               
            summary["total_duration_ms"] += data.get("duration_ms", 0)
        
        return summary
    finally:
        session.close()

async def execute_workflow(run_id: str):
    """
    Execute the ingestion workflow:
    1. List files in raw bucket
    2. Validate each file
    3. Route valid -> processed, invalid -> quarantine
    4. Record metrics
    """
    session = get_session()
    try:
        run = session.query(WorkflowRunDB).filter(WorkflowRunDB.run_id == run_id).first()
        if not run:
            return
        
        run.status = "running"
        run.started_at = datetime.datetime.utcnow()
        session.commit()
        
        # Record start metric
        _record_metric(session, run_id, run.workflow_name, 
                      "workflow_started", {"environment": run.environment}, run.environment)
        
        # Step 1: List files from raw bucket
        files = await storage_client.list_files("ingestion-raw")
        
        if not files:
            run.status = "completed"
            run.completed_at = datetime.datetime.utcnow()
            _record_metric(session, run_id, run.workflow_name,
                          "workflow_completed", {"status": "success", "files_processed": 0}, run.environment)
            session.commit()
            return
        
        processed_count = 0
        invalid_count = 0
        
        for file_key in files:
            try:
                content = await storage_client.get_file("ingestion-raw", file_key)
                
                # Step 2: Validate
                validation_result = _validate_csv(content, file_key)
                
                if validation_result["valid"]:
                    # Step 3a: Move to valid bucket
                    await storage_client.put_file("ingestion-valid", file_key, content)
                    _record_metric(session, run_id, run.workflow_name,
                                  "file_valid", {"file": file_key}, run.environment)
                    
                    # Step 4: Process valid file
                    processed_content = _process_file(content, file_key)
                    processed_key = f"processed_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{file_key}"
                    await storage_client.put_file("ingestion-processed", processed_key, processed_content)
                    _record_metric(session, run_id, run.workflow_name,
                                  "file_processed", {"file": file_key, "output": processed_key}, run.environment)
                    processed_count += 1
                else:
                    # Step 3b: Quarantine invalid file
                    await storage_client.put_file("ingestion-quarantine", file_key, content)
                    _record_metric(session, run_id, run.workflow_name,
                                  "file_invalid", {
                                      "file": file_key,
                                      "errors": validation_result["errors"]
                                  }, run.environment)
                    invalid_count += 1
                    
            except Exception as e:
                _record_metric(session, run_id, run.workflow_name,
                              "file_error", {"file": file_key, "error": str(e)}, run.environment)
        
        run.status = "completed"
        run.completed_at = datetime.datetime.utcnow()
        _record_metric(session, run_id, run.workflow_name,
                      "workflow_completed", {
                          "status": "success",
                          "files_processed": processed_count,
                          "files_invalid": invalid_count
                      }, run.environment)
        session.commit()
        
    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.datetime.utcnow()
        _record_metric(session, run_id, run.workflow_name,
                      "workflow_completed", {"status": "failed", "error": str(e)}, run.environment)
        session.commit()


def _validate_csv(content: str, filename: str) -> dict:
    """Validate CSV file structure and content."""
    import csv
    import io
    
    required_columns = ["partner_id", "date", "amount", "currency"]
    errors = []
    
    try:
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            return {"valid": False, "errors": ["Empty or unreadable CSV"]}
        
        # Check header
        missing = [c for c in required_columns if c not in reader.fieldnames]
        if missing:
            errors.append(f"Missing columns: {', '.join(missing)}")
            return {"valid": False, "errors": errors}
        
        # Validate each row
        row_num = 1
        for row in reader:
            row_num += 1
            if not row.get("partner_id", "").strip():
                errors.append(f"Row {row_num}: Empty partner_id")
            if not row.get("date", "").strip():
                errors.append(f"Row {row_num}: Empty date")
            try:
                amount = float(row.get("amount", ""))
                if amount < 0:
                    errors.append(f"Row {row_num}: Negative amount")
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: Invalid amount")
            if not row.get("currency", "").strip():
                errors.append(f"Row {row_num}: Empty currency")
        
        return {"valid": len(errors) == 0, "errors": errors}
        
    except Exception as e:
        return {"valid": False, "errors": [f"Parse error: {str(e)}"]}


def _process_file(content: str, filename: str) -> str:
    """Process a valid CSV file - normalizes and enriches data."""
    import csv
    import io
    from datetime import datetime
    
    reader = csv.DictReader(io.StringIO(content))
    output = io.StringIO()
    
    # Add processing metadata columns
    fieldnames = reader.fieldnames + ["processed_at", "processing_version"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    now = datetime.utcnow().isoformat()
    for row in reader:
        row["processed_at"] = now
        row["processing_version"] = "1.0.0"
        writer.writerow(row)
    
    return output.getvalue()


def _record_metric(session, run_id, workflow_name, event_type, event_data, environment):
    """Record a metric event to the database."""
    try:
        metric = MetricsDB(
            run_id=run_id,
            workflow_name=workflow_name,
            event_type=event_type,
            event_data=json.dumps(event_data),
            environment=environment,
            created_at=datetime.datetime.utcnow()
        )
        session.add(metric)
        session.commit()
    except:
        session.rollback()