"""
Pydantic models for the FloCI workflow engine API.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime


class WorkflowRun(BaseModel):
    """Represents a single workflow execution."""
    run_id: str
    workflow_name: str
    status: str  # created, running, completed, failed, retrying
    environment: str  # dev, test, prod
    source_file: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class WorkflowCreate(BaseModel):
    """Request model for creating a new workflow run."""
    name: str
    environment: str = "dev"
    source_file: Optional[str] = None
    start_immediately: bool = True


class WorkflowRunResponse(BaseModel):
    """Response model for workflow run operations."""
    run_id: str
    workflow_name: str
    status: str
    environment: str = "dev"
    source_file: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class WorkflowEvent(BaseModel):
    """A workflow lifecycle event."""
    run_id: str
    event_type: str
    event_data: Dict[str, Any]
    timestamp: datetime


class MetricsRecord(BaseModel):
    """Metrics recording request."""
    run_id: str
    workflow_name: str
    event_type: str
    event_data: Dict[str, Any]
    environment: str = "dev"


class EnvironmentConfig(BaseModel):
    """Environment-specific configuration."""
    name: str
    storage_bucket_raw: str
    storage_bucket_valid: str
    storage_bucket_quarantine: str
    storage_bucket_processed: str
    schedule_interval: str = "*/5 * * * *"
    validation_rules: Optional[Dict[str, Any]] = None