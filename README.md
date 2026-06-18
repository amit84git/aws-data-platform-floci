# FloCI Data Platform - Event-Driven Data Ingestion Pipeline

> **FloCI** (Federated Local Cloud Infrastructure) is a self-contained, event-driven data ingestion platform designed for local-first execution. It validates partner CSV files, routes good data to a dedicated bucket, quarantines bad data to another bucket, and writes all pipeline events to an audit S3 bucket for security and compliance. **No PostgreSQL, no cron jobs** - fully event-driven.

## Quick Start

### Prerequisites

- **Docker** and **Docker Compose** (for local platform)
- **Python 3.11+** (for bootstrapping and scripts)
- **curl** and **bash** (for API interaction)

### One-Command Bootstrap

```bash
# Start the entire platform
./scripts/bootstrap.sh

# Or specify an environment
./scripts/bootstrap.sh dev
./scripts/bootstrap.sh test
./scripts/bootstrap.sh prod
```

### What Gets Bootstrapped

The bootstrap script provisions:

| Service                   | Purpose                                   | URL                        |
| ------------------------- | ----------------------------------------- | -------------------------- |
| **S3 Event Router**       | EventBridge-triggered Lambda (REST API)   | http://localhost:8081/docs |
| **EventBridge Simulator** | Watches S3 for new files, triggers router | (internal)                 |
| **MinIO**                 | S3-compatible object storage              | http://localhost:9001      |
| **Grafana**               | Observability via S3 audit logs           | http://localhost:3000      |

Sample data is automatically seeded into MinIO's `ingestion-raw` bucket:

- **Valid files:** `sample.csv`, `second_valid.csv` (5 and 3 rows, all columns present)
- **Invalid files:** `missing_column.csv` (missing `currency`), `bad_data.csv` (multiple data errors), `empty_file.csv` (headers only, no rows)

Once seeded, the EventBridge Simulator automatically detects the new files and triggers the routing pipeline.

### Triggering a Manual Event

```bash
# Trigger processing of a file directly (simulates EventBridge event)
curl -X POST http://localhost:8081/api/v1/process-event \
  -H "Content-Type: application/json" \
  -d '{"file_key":"sample.csv","content":"partner_id,date,amount,currency\n1,2026-01-01,100,USD"}'

# Trigger via S3 notification (fetches from MinIO)
curl -X POST http://localhost:8081/api/v1/process-s3-event \
  -H "Content-Type: application/json" \
  -d '{"bucket":"ingestion-raw","key":"sample.csv"}'

# Health check
curl http://localhost:8081/api/v1/health
```

### Upload a New File (EventBridge Auto-Triggers Processing)

```bash
# Upload a file to MinIO raw bucket - EventBridge auto-detects and processes it
python3 -c "
import boto3
client = boto3.client('s3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin',
)
client.put_object(
    Bucket='ingestion-raw',
    Key='my_partner_data.csv',
    Body=b'partner_id,date,amount,currency\n1,2026-01-01,150.50,USD'
)
print('File uploaded - EventBridge will auto-trigger processing')
"
```

### Access Grafana

1. Open http://localhost:3000
2. Login: `admin` / `admin`
3. Navigate to **Dashboards > FloCI > FloCI Partner Ingestion Dashboard**

## Project Structure

```
├── floci/                          # FloCI platform services
│   ├── docker-compose.yml          # Local platform orchestration
│   ├── Dockerfile.s3_event_router  # Event Router container build
│   ├── Dockerfile.eventbridge      # EventBridge Simulator build
│   ├── router_server.py            # FastAPI wrapper for S3 Event Router Lambda
│   ├── eventbridge_simulator.py    # Watches S3, triggers router on new objects
│   ├── requirements.txt            # Python dependencies
│   └── engine/                     # Legacy engine (deprecated, kept for reference)
│       ├── main.py
│       ├── models.py
│       ├── db.py
│       └── storage.py
├── lambdas/                        # Lambda function implementations
│   ├── s3_event_router/app.py      # ** Main: EventBridge-triggered S3 router **
│   ├── validator/app.py            # Legacy: CSV validation (used internally by router)
│   ├── processor/app.py            # Legacy: CSV processing (used internally by router)
│   ├── quarantine/app.py           # Legacy: quarantine (used internally by router)
│   ├── metrics/app.py              # Legacy: metrics (replaced by audit logger)
│   └── audit_logger/app.py         # ** New: S3 audit logging Lambda **
├── statemachine/                   # Legacy: Step Functions definitions
│   └── ingestion.asl.json
├── terraform/                      # Infrastructure as Code
│   ├── modules/platform/           # Reusable platform module
│   └── envs/{dev,test,prod}/       # Environment configs
├── grafana/                        # Grafana provisioning
│   ├── dashboards/                 # Dashboard definitions
│   └── datasources/                # Datasource definitions
├── sample-data/                    # Test data
│   ├── valid/                      # Valid CSV files
│   └── invalid/                    # Invalid CSV files
├── scripts/                        # Operational scripts
│   ├── bootstrap.sh                # One-command platform setup
│   └── replay.sh                   # Quarantine replay utility
├── ARCHITECTURE.md                 # Design decisions & tradeoffs
├── OPERATIONS.md                   # Operations, failures, reruns
├── GRAFANA.md                      # Grafana dashboard guide
└── AI_USAGE.md                     # AI usage disclosure
```

## Architecture Overview

```
File Drop (S3 PutObject) ──► EventBridge Simulator ──► S3 Event Router Lambda
                                                           │
                                                     ┌─────┴─────┐
                                                     │           │
                                               Valid CSV    Invalid CSV
                                                     │           │
                                                     v           v
                                              ingestion-  ingestion-
                                              good        quarantine
                                                     │           │
                                                     └─────┬─────┘
                                                           │
                                                      ingestion-
                                                      audit (logs)
                                                           │
                                                           v
                                              ✗ Source file deleted
                                              from ingestion-raw
```

**Key differences from traditional architectures:**

- **No PostgreSQL database** - all state is inferred from S3 bucket contents
- **No cron jobs** - EventBridge detects new files in real-time
- **Complete audit trail** - every pipeline event is logged to the audit S3 bucket
- **Fully event-driven** - files flow through the pipeline immediately upon arrival
- **Source cleanup** - original files are automatically deleted from the raw bucket after processing

## Teardown

```bash
# Stop all containers and clean up
docker compose -f floci/docker-compose.yml down -v

# Remove local data
rm -rf .data/
```

## Requirements Met

| #   | Requirement                        | Implementation                                              |
| --- | ---------------------------------- | ----------------------------------------------------------- |
| 1   | Three environments (dev/test/prod) | Terraform envs + Docker Compose env vars                    |
| 2   | Environment-specific config        | Terraform modules per env, isolated buckets                 |
| 3   | S3-compatible ingestion            | MinIO with S3 API (boto3 client)                            |
| 4   | File validation                    | CSV column/type/format checks in S3 Event Router            |
| 5   | Quarantine isolation               | Invalid files routed to quarantine bucket + manifest        |
| 6   | Downstream artifact                | Enriched CSV with metadata columns in good bucket           |
| 7   | Audit logging                      | All pipeline events logged to S3 audit bucket               |
| 8   | Event-driven                       | EventBridge Simulator triggers on S3 object creation        |
| 9   | No PostgreSQL                      | All state inferred from S3 bucket contents + audit logs     |
| 10  | No cron jobs                       | EventBridge detects new files on arrival (poll-free on AWS) |
| 11  | Failure scenario                   | bad_data.csv with 4 different validation errors             |

## Known Limitations

1. **Local EventBridge Simulator uses polling:** MinIO doesn't support native S3 event notifications. The EventBridge Simulator polls every 5 seconds. On AWS, native EventBridge rules would eliminate this.
2. **Single-node:** All services run on one machine via Docker. Not horizontally scalable.
3. **No encryption at rest:** MinIO in local mode. Production should enable SSE-S3 or KMS.
4. **No auth:** API endpoints are open. Production would require API keys or IAM.
5. **S3 audit log querying:** Without Athena, audit logs are browsed via MinIO console. Production would use Athena or CloudWatch Logs Insights.

## What's Next

- Add AWS deployment support with Terraform + S3 state backend
- Implement Athena/Glue for SQL querying of audit logs
- Add notification channels (Slack, PagerDuty) for quarantine events
- Implement data quality scoring and lineage tracking
- Add CI/CD pipeline for automated Terraform apply
