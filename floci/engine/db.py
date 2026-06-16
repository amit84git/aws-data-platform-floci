"""
Database models and session management for FloCI workflow state.
"""

import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "FLOCI_DB_URL",
    "postgresql+psycopg2://floci:floci@localhost:5432/floci"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class WorkflowRunDB(Base):
    """Database model for workflow runs."""
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), unique=True, nullable=False, index=True)
    workflow_name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="created")
    environment = Column(String(50), nullable=False, default="dev")
    source_file = Column(String(1024), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MetricsDB(Base):
    """Database model for workflow metrics."""
    __tablename__ = "workflow_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False, index=True)
    workflow_name = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_data = Column(Text, nullable=True)  # JSON string
    environment = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_session():
    """Get a new database session."""
    return SessionLocal()