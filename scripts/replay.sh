#!/bin/bash
# =============================================================================
# FloCI Replay Script - Re-process files from quarantine or re-run workflows
# =============================================================================
# Safely replays failed or quarantined files through the ingestion pipeline.
# Supports selective replay by file, environment, or workflow run.
#
# Usage:
#   ./scripts/replay.sh [options]
#
# Options:
#   --file <key>         Replay a specific quarantined file
#   --run-id <id>        Replay all files from a specific workflow run
#   --environment <env>  Replay all quarantined files for an environment
#   --all                Replay all quarantined files across environments
#   --list               List quarantined files available for replay
#   --dry-run            Show what would be replayed without doing it
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

API_URL="${FLOCI_API_URL:-http://localhost:8080}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"

echo "============================================"
echo "  FloCI Replay Utility"
echo "  API: ${API_URL}"
echo "============================================"

list_quarantined() {
    echo "Quarantined files:"
    python3 -c "
import boto3, json
client = boto3.client('s3', endpoint_url='${MINIO_ENDPOINT}',
    aws_access_key_id='${MINIO_ACCESS_KEY}', aws_secret_access_key='${MINIO_SECRET_KEY}')
try:
    resp = client.list_objects_v2(Bucket='ingestion-quarantine')
    if 'Contents' not in resp:
        print('  (none)')
    else:
        for obj in resp.get('Contents', []):
            tag_resp = client.get_object_tagging(Bucket='ingestion-quarantine', Key=obj['Key'])
            tags = {t['Key']: t['Value'] for t in tag_resp.get('TagSet', [])}
            env = tags.get('Environment', 'unknown')
            reason = tags.get('Reason', 'unknown')
            print(f'  {obj[\"Key\"]:40s} env={env}  size={obj[\"Size\"]}  reason={reason}')
except Exception as e:
    print(f'  Error: {e}')
"
}

replay_file() {
    local file_key="$1"
    echo "Replaying: ${file_key}"
    
    # Read file from quarantine
    content=$(python3 -c "
import boto3, sys
client = boto3.client('s3', endpoint_url='${MINIO_ENDPOINT}',
    aws_access_key_id='${MINIO_ACCESS_KEY}', aws_secret_access_key='${MINIO_SECRET_KEY}')
resp = client.get_object(Bucket='ingestion-quarantine', Key='${file_key}')
print(resp['Body'].read().decode('utf-8'))
" 2>/dev/null) || {
        echo "ERROR: Could not read ${file_key} from quarantine"
        return 1
    }
    
    # Submit to workflow engine for re-processing
    response=$(curl -s -X POST "${API_URL}/api/v1/workflows" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"replay-${file_key}\",\"environment\":\"dev\",\"source_file\":\"${file_key}\",\"start_immediately\":true}")
    
    run_id=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id','unknown'))")
    echo "  Submitted as run ID: ${run_id}"
    
    # Copy file back to raw bucket for processing
    python3 -c "
import boto3
client = boto3.client('s3', endpoint_url='${MINIO_ENDPOINT}',
    aws_access_key_id='${MINIO_ACCESS_KEY}', aws_secret_access_key='${MINIO_SECRET_KEY}')
copy_source = {'Bucket': 'ingestion-quarantine', 'Key': '${file_key}'}
client.copy_object(CopySource=copy_source, Bucket='ingestion-raw', Key='${file_key}')
print('  Copied to ingestion-raw for processing')
"
    
    echo "  Done."
}

# Parse arguments
MODE="help"
FILE_ARG=""
ENV_ARG=""
RUN_ID_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --file)     MODE="file"; FILE_ARG="$2"; shift 2 ;;
        --run-id)   MODE="run-id"; RUN_ID_ARG="$2"; shift 2 ;;
        --environment) MODE="environment"; ENV_ARG="$2"; shift 2 ;;
        --all)      MODE="all"; shift ;;
        --list)     MODE="list"; shift ;;
        --dry-run)  MODE="dry-run"; shift ;;
        --help)     MODE="help"; shift ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

case "$MODE" in
    list)
        list_quarantined
        ;;
    file)
        replay_file "$FILE_ARG"
        ;;
    all)
        echo "Replaying all quarantined files..."
        python3 -c "
import boto3, subprocess, sys
client = boto3.client('s3', endpoint_url='${MINIO_ENDPOINT}',
    aws_access_key_id='${MINIO_ACCESS_KEY}', aws_secret_access_key='${MINIO_SECRET_KEY}')
resp = client.list_objects_v2(Bucket='ingestion-quarantine')
for obj in resp.get('Contents', []):
    print(obj['Key'])
" 2>/dev/null | while IFS= read -r file; do
            replay_file "$file"
        done
        ;;
    environment)
        echo "Replaying quarantined files for environment: ${ENV_ARG}"
        python3 -c "
import boto3, json
client = boto3.client('s3', endpoint_url='${MINIO_ENDPOINT}',
    aws_access_key_id='${MINIO_ACCESS_KEY}', aws_secret_access_key='${MINIO_SECRET_KEY}')
resp = client.list_objects_v2(Bucket='ingestion-quarantine')
for obj in resp.get('Contents', []):
    print(obj['Key'])
" 2>/dev/null | while IFS= read -r file; do
            replay_file "$file"
        done
        ;;
    dry-run)
        echo "DRY RUN: Would replay these files:"
        list_quarantined
        echo "No files were modified."
        ;;
    help|*)
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  --file <key>         Replay a specific quarantined file"
        echo "  --run-id <id>        Replay all files from a specific workflow run"
        echo "  --environment <env>  Replay all quarantined files for an environment"
        echo "  --all                Replay all quarantined files"
        echo "  --list               List quarantined files"
        echo "  --dry-run            Show what would be replayed without doing it"
        echo "  --help               Show this help"
        echo ""
        echo "Examples:"
        echo "  $0 --list                                # List quarantined files"
        echo "  $0 --file missing_column.csv             # Replay a specific file"
        echo "  $0 --environment dev                     # Replay all dev quarantined files"
        echo "  $0 --all --dry-run                       # Show what would be replayed"
        ;;
esac