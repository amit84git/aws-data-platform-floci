# Architecture

## Overview

FloCI is a **local-first data ingestion platform** that validates, processes, and routes partner CSV files. It is designed to be fully reproducible on any machine with Docker, requiring no cloud credentials. The architecture follows a **fully event-driven pattern** with **no PostgreSQL or cron dependencies** - everything is routed through S3-compatible object storage.

## Key Design Decisions

### 1. EventBridge + Event-Driven Architecture Instead of Cron/PostgreSQL

**Decision:** Replace PostgreSQL-based metadata storage and cron-based scheduling with a fully event-driven architecture using EventBridge-style triggers.

**Rationale:**

- **No metadata database needed:** PostgreSQL was previously used for workflow state and metrics. Now all pipeline state is inferred from S3 bucket contents (good data bucket, quarantine bucket) and the complete audit trail is stored as structured JSON logs in the audit S3 bucket.
- **No cron scheduling:** The EventBridge Simulator listens for S3 object creation events (`S3:ObjectCreated:*`) and triggers the S3 Event Router Lambda immediately. In production on AWS, native EventBridge rules would handle this without any polling.
- **True event-driven pipeline:** Files flow through the pipeline based on events, not scheduled polls. This reduces latency from "next cron interval" to near-real-time.
- **Simpler operational model:** Fewer services to manage (no PostgreSQL, no scheduler, no metrics DB).

**Tradeoff:** Local EventBridge Simulator uses lightweight polling (5-second intervals) to detect new S3 objects since MinIO doesn't support native S3 event notifications. In production AWS, this is replaced with native EventBridge rules with zero polling overhead.

### 2. MinIO Instead of Production S3

**Decision:** Use MinIO for S3-compatible object storage.

**Rationale:**

- Provides the exact S3 API (`GetObject`, `PutObject`, `ListObjectsV2`) so the storage layer is API-identical to AWS S3.
- No cloud account needed. Reproducible on any machine.
- The Terraform module provisions real S3 buckets with the same schema for actual AWS deployment.

**Tradeoff:** MinIO lacks S3 features like native event notifications, replication, and intelligent tiering. The EventBridge Simulator compensates for the event notification gap locally.

### 3. S3 Event Router Lambda (Single Lambda Instead of Multiple)

**Decision:** Combine validation, processing, routing, audit logging, and source cleanup into a single S3 Event Router Lambda.

**Rationale:**

- **Simpler data flow:** A single Lambda reads from the source bucket, validates, enriches good data, quarantines bad data, writes audit logs, and deletes the original file from the source bucket - all in one invocation. No need for a state machine or multiple chained functions.
- **Lower latency:** File is processed in a single pass rather than being read, written, and re-read by multiple functions.
- **Easier debugging:** Complete processing trace for a file is in one log entry.
- **Still AWS Lambda-compatible:** The `lambda_handler(event, context)` interface is identical to AWS Lambda, so it can run on AWS Lambda without modification.
- The separation of concerns is maintained internally via clean function boundaries (`_validate_csv`, `_process_csv`, `_write_audit_log`).

**Tradeoff:** Less granular scaling (the entire pipeline scales as one unit vs. individual functions). Mitigation: On AWS, this can be split into separate EventBridge-targeted Lambdas with S3 as the event bus.

### 4. S3-Based Audit Logging Instead of PostgreSQL Metrics

**Decision:** Replace PostgreSQL metrics storage with structured JSON audit logs written directly to an S3 audit bucket.

**Rationale:**

- **Complete audit trail:** Every pipeline event (file read, validation result, routing decision, error) is logged as a structured JSON document with timestamps, severity, and contextual metadata.
- **Immutable logs:** Once written to S3, audit logs cannot be modified - providing a tamper-evident audit trail for security and compliance.
- **No database to manage:** Audit logs can be queried using S3 Select, Athena, or the built-in metrics API endpoint.
- **Cost-effective:** S3 storage is significantly cheaper than running a database for log storage.
- **Grafana can still visualize:** Grafana's Infinity datasource queries the S3 Event Router's `GET /api/v1/metrics` REST API, which aggregates audit logs on-the-fly.

**Tradeoff:** S3 lacks real-time query capabilities of PostgreSQL. Mitigation: The S3 Event Router exposes a `GET /api/v1/metrics` endpoint that aggregates the last 24 hours of audit logs into pre-computed counts, event breakdowns, and hourly timelines — suitable for Grafana rendering without external query engines.

### 5. REST Metrics API Instead of Dedicated Metrics Database

**Decision:** Provide observability via a REST API endpoint (`GET /api/v1/metrics`) on the S3 Event Router that aggregates S3 audit logs in-memory, rather than running a separate metrics database or Prometheus.

**Rationale:**

- **No additional infrastructure needed:** The metrics endpoint runs in the same process as the router — no separate database or service to manage.
- **Self-contained observability:** The router reads audit logs from MinIO's `ingestion-audit` bucket, aggregates them (event types, severities, hourly timeline), and returns JSON suited for Grafana's Infinity datasource.
- **Consistent with no-PostgreSQL philosophy:** All state lives in S3; the metrics API is just a read-only aggregator.
- **Zero configuration:** No schema migrations, retention policies, or connection strings.

**Tradeoff:** The aggregation is in-memory and reads all audit logs from the last 24 hours each time the endpoint is called. At scale, this would be replaced with Athena, S3 Select, or a Prometheus exporter. The 24-hour window is suitable for operational dashboards but not for historical trend analysis.

### 6. Single Lambda Function with Clean Internal Separation

**Decision:** The S3 Event Router Lambda handles the entire pipeline internally with well-separated concerns.

**Rationale:**

- The `lambda_handler` function reads the event, extracts file(s) to process, and orchestrates the pipeline.
- `_validate_csv` / `_validate_row` handle validation logic (same as the old validator Lambda).
- `_process_csv` handles enrichment (same as the old processor Lambda).
- `_write_audit_log` handles structured logging (replaces the old metrics and audit_logger Lambdas).
- Each internal function is independently testable and has a clear responsibility.
- The interface mirrors AWS Lambda's exactly — `lambdas/s3_event_router/app.py` can run on real AWS Lambda without modification.

**Note on legacy Lambdas:** The `lambdas/validator/`, `lambdas/processor/`, `lambdas/quarantine/`, `lambdas/metrics/`, and `lambdas/audit_logger/` directories are kept for reference but are not used at runtime. All functionality has been consolidated into `lambdas/s3_event_router/app.py`.

## Data Flow

```
Partner File Drop (S3 PutObject)
       │
       v
┌──────────────────┐     ┌──────────────────────────────┐
│  MinIO           │     │  EventBridge Simulator       │
│  (ingestion-raw) │────►│  (watches for new objects)   │
└──────────────────┘     └──────────────┬───────────────┘
                                        │
                                        v
                             ┌──────────────────────┐
                             │  S3 Event Router     │
                             │  Lambda (FastAPI)    │
                             │                      │
                             │  1. Read file from   │
                             │     ingestion-raw    │
                             │  2. Validate CSV     │
                             │  3. Route:           │
                             │    ┌─ Valid ───┐     │
                             │    │ Good Data │     │
                             │    │  Bucket   │     │
                             │    └───────────┘     │
                             │    ┌─ Invalid ─┐     │
                             │    │ Quarantine │     │
                             │    │  Bucket    │     │
                             │    └───────────┘     │
                             │  4. Write Audit Log  │
                             │  5. Delete source    │
                             │     file from raw    │
                             └──────────┬───────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    v                   v                   v
           ┌────────────┐    ┌──────────────┐    ┌──────────────┐
           │ MinIO      │    │ MinIO        │    │ MinIO        │
           │(ingestion- │    │(ingestion-   │    │(ingestion-   │
           │ good)      │    │ quarantine)  │    │ audit)       │
           └────────────┘    └──────────────┘    └──────────────┘
                                                   │
                                                   v
                                           ┌──────────────────┐
                                           │  S3 Event Router │
                                           │ GET /api/v1/     │
                                           │   metrics        │
                                           └────────┬─────────┘
                                                    │
                                                    v
                                           ┌──────────────────┐
                                           │  Grafana         │
                                           │ (Infinity        │
                                           │  datasource →    │
                                           │  REST API)       │
                                           └──────────────────┘
```

### Observability Data Flow

Grafana does **not** read from MinIO directly. Instead:

1. The S3 Event Router exposes `GET /api/v1/metrics` which:
   - Lists audit log objects from MinIO's `ingestion-audit` bucket (last 24 hours)
   - Reads and parses each JSON log entry
   - Aggregates counts by event type, severity, and hourly timeline
   - Returns a JSON response with pre-computed metrics
2. Grafana's Infinity datasource plugin queries this REST endpoint
3. Each dashboard panel extracts its value using JSONPath expressions

This eliminates the need for a dedicated metrics database or direct S3 querying from Grafana.

## Environment Strategy

Three environments (`dev`, `test`, `prod`) are supported for Terraform/AWS deployment:

| Aspect        | dev                           | test                           | prod                                              |
| ------------- | ----------------------------- | ------------------------------ | ------------------------------------------------- |
| Bucket prefix | `floci-dev-`                  | `floci-test-`                  | `floci-prod-`                                     |
| Event trigger | EventBridge Simulator (5s)    | EventBridge Simulator (10s)    | Native AWS EventBridge (real-time)                |
| Versioning    | Disabled                      | Enabled                        | Enabled + lifecycle                               |
| Tags          | `CostCenter: engineering-dev` | `CostCenter: engineering-test` | `CostCenter: operations-prod`, `Compliance: soc2` |

Environment isolation in Terraform is achieved through separate `main.tf` files in `terraform/envs/{dev,test,prod}/`, each calling the shared `modules/platform` module with different variables.

**Local environment:** The Docker Compose stack runs with `ENVIRONMENT=local` (not `dev`/`test`/`prod`). This is a dedicated environment variable that doesn't overlap with the Terraform environments.

## Bucket Structure

| Bucket                 | Purpose                                          | Access Pattern           |
| ---------------------- | ------------------------------------------------ | ------------------------ |
| `ingestion-raw`        | Source bucket - partners drop CSV files here     | Write: Partners / S3     |
| `ingestion-good`       | Valid, processed CSV data with enrichment        | Read: Downstream systems |
| `ingestion-quarantine` | Invalid/inconsistent files with manifest         | Read: Manual review      |
| `ingestion-audit`      | Structured JSON audit logs (all pipeline events) | Read: Security, audit    |

## API Endpoints

The S3 Event Router (FastAPI) exposes the following REST endpoints:

| Endpoint                   | Method | Purpose                                                            |
| -------------------------- | ------ | ------------------------------------------------------------------ |
| `/api/v1/process-event`    | POST   | Simulate EventBridge trigger; routes a file through the pipeline   |
| `/api/v1/process-s3-event` | POST   | Simulate S3 notification; fetches file from MinIO and processes it |
| `/api/v1/metrics`          | GET    | Aggregate pipeline metrics from S3 audit logs (last 24h)           |
| `/api/v1/health`           | GET    | Health check                                                       |

## Security & Network Boundary

**Decision:** All S3 buckets have public access blocks enabled.

**Explanation:** Even though the demo runs locally, the Terraform configuration explicitly blocks all public access:

```hcl
resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

In production, this would be combined with VPC endpoints, bucket policies restricting access to the Lambda IAM role, and KMS encryption.

**Tradeoff:** Blocking public access prevents internet-based partners from directly uploading files. In production, partners would upload via a presigned URL API gateway, or the buckets would be accessed through a VPC endpoint.

## Audit Log Schema

Each audit log entry is a structured JSON document stored in the `ingestion-audit` bucket:

```json
{
  "timestamp": "2026-06-16T20:30:00.123456+00:00",
  "event_type": "file_routed_good",
  "source": "s3_event_router",
  "severity": "INFO",
  "details": {
    "file_key": "sample.csv",
    "output_key": "good_20260616_203000_sample.csv",
    "row_count": 5,
    "destination_bucket": "ingestion-good"
  },
  "service": "floci-ingestion-pipeline",
  "environment": "dev"
}
```

### Event Types

| Event Type                 | Severity | Description                                     |
| -------------------------- | -------- | ----------------------------------------------- |
| `file_read`                | INFO     | File read from source bucket                    |
| `file_routed_good`         | INFO     | Valid file routed to good data bucket           |
| `file_routed_quarantine`   | WARN     | Invalid file routed to quarantine bucket        |
| `file_deleted_from_source` | INFO     | Original file deleted from raw bucket           |
| `file_delete_failed`       | WARN     | Failed to delete source file (non-fatal)        |
| `file_error`               | ERROR    | Error processing file (S3 or unexpected error)  |
| `batch_completed`          | INFO     | Summary of all files processed in a batch       |
| `no_files`                 | WARN     | No files to process (unrecognized event format) |

Audit log keys follow the pattern: `audit-logs/{YYYY}/{MM}/{DD}/{source}/{event_type}/{timestamp}.json`

## Grafana Integration

Grafana uses the **Infinity datasource plugin** to query the S3 Event Router's REST API:

1. **Datasource:** `FloCI Audit Logs (S3)` (Infinity plugin, type: `yesoreyeram-infinity-datasource`)
2. **Query URL:** `http://floci-s3-event-router:8081/api/v1/metrics`
3. **Panels:** Stat, bar chart, time series, and table panels extract values via JSONPath

This approach:

- Requires no database setup (no PostgreSQL, no Prometheus)
- Uses the same audit logs stored in S3 for both compliance and observability
- Is fully self-contained within the Docker Compose stack
