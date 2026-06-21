# Operations Guide

## Architecture Changes

This version of FloCI has been refactored from a PostgreSQL + cron-based architecture to a fully event-driven, S3-native approach:

- **No PostgreSQL** - All pipeline state is inferred from S3 bucket contents
- **No cron jobs** - EventBridge detects new files on arrival
- **S3 audit logging** - All pipeline events written as structured JSON to the audit bucket
- **Single S3 Event Router Lambda** - Handles validation, routing, and audit logging

## Service Components

| Service                       | Description                                                 | Port |
| ----------------------------- | ----------------------------------------------------------- | ---- |
| `minio`                       | S3-compatible object storage (MinIO)                        | 9000 |
| `minio-init`                  | Creates buckets (raw, good, quarantine, audit) on startup   | -    |
| `floci-s3-event-router`       | FastAPI wrapper: routes files + exposes metrics REST API    | 8081 |
| `floci-eventbridge-simulator` | Watches S3, triggers router on new objects (polls every 5s) | -    |
| `grafana`                     | Observability via Infinity datasource querying metrics API  | 3000 |

## S3 Buckets

| Bucket                 | Purpose                                          | Access Pattern           |
| ---------------------- | ------------------------------------------------ | ------------------------ |
| `ingestion-raw`        | Source bucket - partners drop CSV files here     | Write: Partners / S3     |
| `ingestion-good`       | Valid, processed CSV data with enrichment        | Read: Downstream systems |
| `ingestion-quarantine` | Invalid/inconsistent files with manifest         | Read: Manual review      |
| `ingestion-audit`      | Structured JSON audit logs (all pipeline events) | Read: Security, audit    |

## How the Pipeline Works

1. **File arrives** in `ingestion-raw` bucket (via MinIO console, API, or S3 put)
2. **EventBridge Simulator** detects the new object (polls every 5 seconds)
3. **S3 Event Router Lambda** is triggered via HTTP with the file content
4. Lambda performs:
   - **Reads** the file from `ingestion-raw`
   - **Validates** CSV structure and data quality
   - **Routes** valid data to `ingestion-good` with enrichment columns
   - **Routes** invalid data to `ingestion-quarantine` with manifest
   - **Logs** the entire pipeline event to `ingestion-audit`
   - **Deletes** the original file from `ingestion-raw` (post-processing cleanup)
5. **Result** is reflected immediately in the S3 bucket contents

## Common Operations

### Viewing Pipeline Results

Check bucket contents to see routing results:

```bash
# Using MinIO client (mc)
docker exec floci-minio mc ls local/ingestion-good/
docker exec floci-minio mc ls local/ingestion-quarantine/
docker exec floci-minio mc ls local/ingestion-audit/

# Or using Python/boto3
python3 -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin')
for b in ['ingestion-good', 'ingestion-quarantine', 'ingestion-audit']:
    resp = s3.list_objects_v2(Bucket=b)
    keys = [o['Key'] for o in resp.get('Contents', [])]
    print(f'{b}: {len(keys)} files')
    for k in keys[:5]:
        print(f'  - {k}')
"
```

### Viewing Audit Logs

Audit logs are stored as structured JSON in the `ingestion-audit` bucket:

```bash
# List audit log files
docker exec floci-minio mc ls --recursive local/ingestion-audit/audit-logs/

# View a specific audit log
docker exec floci-minio mc cat local/ingestion-audit/audit-logs/2026/06/16/...json

# Or via Python
python3 -c "
import boto3, json
s3 = boto3.client('s3', endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin')
resp = s3.list_objects_v2(Bucket='ingestion-audit', Prefix='audit-logs/')
for obj in resp.get('Contents', [])[:3]:
    data = s3.get_object(Bucket='ingestion-audit', Key=obj['Key'])
    print(json.dumps(json.loads(data['Body'].read()), indent=2))
"
```

### Manually Triggering File Processing

There are three ways to trigger file processing:

**1. Upload to MinIO (EventBridge auto-detects):**

```bash
python3 -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin')
with open('sample-data/valid/sample.csv', 'rb') as f:
    s3.put_object(Bucket='ingestion-raw', Key='my_file.csv', Body=f)
print('Uploaded - EventBridge will auto-trigger processing')
"
```

**2. Direct API call to router (with content):**

```bash
curl -X POST http://localhost:8081/api/v1/process-event \
  -H "Content-Type: application/json" \
  -d '{
    "file_key": "test.csv",
    "content": "partner_id,date,amount,currency\n1,2026-01-01,100,USD\n2,2026-01-02,abc,INVALID"
  }'
```

**3. Direct API call to router (fetches from S3):**

```bash
curl -X POST http://localhost:8081/api/v1/process-s3-event \
  -H "Content-Type: application/json" \
  -d '{"bucket": "ingestion-raw", "key": "sample.csv"}'
```

### Viewing Container Logs

```bash
# EventBridge Simulator logs - shows file detection events
docker logs floci-eventbridge-simulator

# S3 Event Router logs - shows validation and routing decisions
docker logs floci-s3-event-router

# Follow logs in real-time
docker logs -f floci-s3-event-router
```

## Failure Scenarios

### 1. Validation Failure (Expected)

If a file has invalid data, it is routed to `ingestion-quarantine` with a manifest:

```
# Quarantine manifest includes:
# - Original file content
# - List of validation errors
# - Timestamp of quarantine
# - Environment information
```

**Check:** Look in `ingestion-quarantine` bucket for files starting with `quarantine_`.

### 2. S3 Connection Failure

If the router cannot connect to MinIO:

```
Error: Could not connect to the endpoint URL "http://minio:9000"
```

**Resolution:**

1. Check MinIO is running: `docker ps | grep floci-minio`
2. Check MinIO logs: `docker logs floci-minio`
3. Restart if needed: `docker compose -f floci/docker-compose.yml restart floci-minio`

### 3. EventBridge Simulator Outage

The simulator maintains a state file (`/tmp/eventbridge_processed_files.json`) to track processed files. If it restarts, it will:

- Load the known files list from the state file
- Process any new files that were added during the outage
- Not re-process files that were already handled

**Check simulator status:**

```bash
docker logs floci-eventbridge-simulator | tail -20
```

### 4. Router API Unavailable

If the router is down when the simulator detects a new file, the simulator will:

1. Log a warning
2. Leave the file in `known_files` list so it will be retried on the next poll cycle
3. Continue polling

## Recovery Procedures

### Re-processing a Quarantined File

```bash
# 1. List quarantined files
docker exec floci-minio mc ls local/ingestion-quarantine/

# 2. Download a quarantined file
docker exec floci-minio mc cat local/ingestion-quarantine/quarantine_20260616_203000_sample.csv > /tmp/quarantined.csv

# 3. Extract the original content (above the manifest section)
# 4. Upload it back to raw bucket
python3 -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin')
with open('/tmp/quarantined.csv', 'rb') as f:
    s3.put_object(Bucket='ingestion-raw', Key='replay_sample.csv', Body=f)
print('Re-uploaded - will be processed by EventBridge')
"
```

### Re-uploading Files After Processing

Since the pipeline automatically deletes files from `ingestion-raw` after processing, you can simply upload the same file again to retrigger processing. The EventBridge Simulator will detect it as a new object.

### Full Pipeline Reset

```bash
# Stop everything
docker compose -f floci/docker-compose.yml down -v

# Clean up data
rm -rf .data/

# Restart
./scripts/bootstrap.sh
```

## Monitoring

### Key Metrics to Watch

1. **Files in good bucket** vs **files in quarantine bucket** - data quality ratio
2. **EventBridge Simulator logs** - detection latency
3. **Router logs** - processing time and error rates
4. **Audit logs in S3** - complete pipeline traceability

### Accessing Metrics via REST API

The S3 Event Router exposes a built-in metrics aggregation endpoint at `GET /api/v1/metrics`. This endpoint reads audit logs from the `ingestion-audit` bucket (last 24 hours) and returns pre-aggregated JSON:

```bash
# Quick check via curl
curl http://localhost:8081/api/v1/metrics

# Example response:
# {
#   "total_events": 7,
#   "good_files": 2,
#   "quarantine_files": 5,
#   "errors": 0,
#   "events_by_type": [
#     {"event_type": "file_routed_good", "count": 2},
#     {"event_type": "file_routed_quarantine", "count": 5},
#     ...
#   ],
#   "events_timeline": [
#     {"time": "2026-06-21T16:00:00", "count": 3},
#     ...
#   ]
# }
```

This endpoint is what Grafana's Infinity datasource queries for dashboard panels.

### Accessing Metrics via Audit Logs (Direct S3)

```bash
# Count good vs quarantine events
python3 -c "
import boto3, json
s3 = boto3.client('s3', endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin')
resp = s3.list_objects_v2(Bucket='ingestion-audit', Prefix='audit-logs/')
good = quarantine = errors = 0
for obj in resp.get('Contents', []):
    data = json.loads(s3.get_object(Bucket='ingestion-audit', Key=obj['Key'])['Body'].read())
    if data['event_type'] == 'file_routed_good': good += 1
    elif data['event_type'] == 'file_routed_quarantine': quarantine += 1
    elif data['severity'] == 'ERROR': errors += 1
print(f'Good: {good}, Quarantine: {quarantine}, Errors: {errors}')
"
```

## Terraform Operations

See `terraform/envs/{dev,test,prod}/` for AWS deployment configurations.

The Terraform module provisions:

- S3 buckets (raw, good, quarantine, audit) with appropriate access policies
- IAM roles and policies for Lambda execution
- S3 EventBridge notifications for real-time triggering
- Lambda functions for the S3 Event Router
- CloudWatch Logs for Lambda monitoring
