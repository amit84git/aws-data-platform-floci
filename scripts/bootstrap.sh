#!/bin/bash
# =============================================================================
# FloCI Platform Bootstrap Script
# =============================================================================
# Provisions the entire local platform: MinIO, EventBridge Simulator,
# S3 Event Router, Grafana. Fully event-driven 
# Usage: ./scripts/bootstrap.sh [environment]
#   environment: dev | test | prod  (default: dev)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENVIRONMENT="${1:-dev}"
COMPOSE_FILE="$PROJECT_ROOT/floci/docker-compose.yml"
DATA_DIR="$PROJECT_ROOT/.data"

echo "============================================"
echo "  FloCI Platform Bootstrap - ${ENVIRONMENT}"
echo "  (Event-Driven - No PostgreSQL, No Cron)"
echo "============================================"

# Step 1: Check prerequisites
echo ""
echo "[1/5] Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is required but not found."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "WARNING: python3 not found, pip install step skipped."; }

# Step 2: Create data directories
echo ""
echo "[2/5] Creating data directories..."
mkdir -p "$DATA_DIR/minio"
mkdir -p "$DATA_DIR/grafana"
echo "  Data directory: $DATA_DIR"

# Step 3: Start infrastructure services (MinIO only - no PostgreSQL)
echo ""
echo "[3/5] Starting infrastructure (MinIO object storage)..."
export ENVIRONMENT
docker compose -f "$COMPOSE_FILE" up -d minio minio-init
echo "  Waiting for MinIO to be healthy..."
sleep 8

# Step 4: Start S3 Event Router and EventBridge Simulator
echo ""
echo "[4/5] Starting S3 Event Router and EventBridge Simulator..."
docker compose -f "$COMPOSE_FILE" up -d floci-s3-event-router floci-eventbridge-simulator
echo "  Waiting for services to initialize..."
sleep 5

# Step 5: Seed sample data and verify
echo ""
echo "[5/5] Seeding sample data and verifying..."
# Copy sample data to MinIO raw bucket - this triggers EventBridge -> Router -> processing
if command -v python3 >/dev/null 2>&1; then
    python3 -c "
import boto3
import os

client = boto3.client('s3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin',
)
bucket = 'ingestion-raw'

valid_dir = '${PROJECT_ROOT}/sample-data/valid'
invalid_dir = '${PROJECT_ROOT}/sample-data/invalid'
import glob

print('  Seeding valid files...')
for f in sorted(glob.glob(f'{valid_dir}/*.csv')):
    key = os.path.basename(f)
    with open(f, 'rb') as fh:
        client.put_object(Bucket=bucket, Key=key, Body=fh)
    print(f'    + Valid: {key}')

print('  Seeding invalid files...')
for f in sorted(glob.glob(f'{invalid_dir}/*.csv')):
    key = os.path.basename(f)
    with open(f, 'rb') as fh:
        client.put_object(Bucket=bucket, Key=key, Body=fh)
    print(f'    + Invalid: {key}')

print('  Sample data seeded - EventBridge will auto-trigger processing')
" 2>/dev/null && echo "  Sample data seeded successfully" || echo "  WARNING: Data seeding skipped"
fi

# Wait for EventBridge to trigger processing
echo "  Waiting for EventBridge to trigger routing pipeline..."
sleep 10

# Verify the platform is running
echo ""
echo "============================================"
echo "  FloCI Platform Status"
echo "============================================"
echo ""
echo "  Services:"
docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "  Access URLs:"
echo "    S3 Event Router API: http://localhost:8081/docs"
echo "    MinIO Console:       http://localhost:9001 (minioadmin / minioadmin)"
echo "    Grafana:             http://localhost:3000 (admin / admin)"
echo ""
echo "  S3 Buckets:"
echo "    ingestion-raw       - Source bucket for partner file drops"
echo "    ingestion-good      - Valid/processed CSV data"
echo "    ingestion-quarantine - Invalid/inconsistent CSV data"
echo "    ingestion-audit     - Audit logs (all pipeline events)"
echo ""
echo "  API Endpoints:"
echo "    POST /api/v1/process-event   - Simulate EventBridge event (trigger routing)"
echo "    POST /api/v1/process-s3-event - Process S3 notification"
echo "    GET  /api/v1/health          - Health check"
echo ""
echo "  How It Works:"
echo "    1. A file is dropped into the 'ingestion-raw' MinIO bucket"
echo "    2. EventBridge Simulator detects the new object (no cron)"
echo "    3. Lambda (S3 Event Router) validates the CSV"
echo "    4. Good data  -> ingestion-good bucket"
echo "    5. Bad data   -> ingestion-quarantine bucket"
echo "    6. All events -> ingestion-audit bucket (audit trail)"
echo ""
echo "  Manual trigger (for testing):"
echo '    curl -X POST http://localhost:8081/api/v1/process-event \\'
echo '      -H "Content-Type: application/json" \\'
echo '      -d "{\\"file_key\\":\\"sample.csv\\",\\"content\\":\\"partner_id,date,amount,currency\\n1,2026-01-01,100,USD\\"}"'
echo ""
echo "============================================"
echo "  Bootstrap complete for environment: ${ENVIRONMENT}"
echo "============================================"