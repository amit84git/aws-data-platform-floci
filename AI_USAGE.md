# AI Usage Disclosure

## Overview

This project was developed with assistance from Cline (an AI coding assistant). Below is a transparent account of how AI was used, what was accepted unchanged, what was changed or rejected, and how the output was validated.

## How AI Was Used

| Task                                                       | AI Role                                            | Human Role                                                                                       |
| ---------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Project scaffolding                                        | Generated initial file structure from requirements | Reviewed structure, adjusted naming, added missing directories                                   |
| Docker Compose configuration                               | Drafted service definitions based on requirements  | Validated port mappings, added health checks, adjusted volume mounts                             |
| FloCI platform services                                    | Generated core router, eventbridge, metrics code   | Added error handling, input validation, enriched audit logging                                   |
| Lambda functions (validator, processor, quarantine, audit) | Generated core validation/processing logic         | Extended validation rules, added edge case handling, enriched quarantine manifests               |
| Terraform configurations                                   | Generated module and environment files             | Added security blocks (public_access_block), versioning, lifecycle policies, IAM least-privilege |
| Grafana dashboard JSON                                     | Generated initial panel structure and queries      | Switched from PostgreSQL to Infinity/S3 datasource, adjusted panel sizing                        |
| Documentation (README, ARCHITECTURE, OPERATIONS, GRAFANA)  | Generated initial drafts from structured prompts   | Reviewed for accuracy, added missing details, adjusted tone for technical audience               |

## What Was Accepted Unchanged

- **Boilerplate code** (Docker Compose service shells, Terraform resource stubs, Python `__init__.py` files)
- **Lambda handler structure** (standard `lambda_handler(event, context)` pattern)
- **Sample data CSV files** — simple format, validated by the router Lambda
- **Audit log JSON schema** — structured logging format for S3 audit trail

## What Was Changed or Rejected

| Item                                | AI Output                                    | Final Decision | Reason                                                                                   |
| ----------------------------------- | -------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------- |
| Airflow-based orchestration         | AI proposed using Airflow with LocalExecutor | **Rejected**   | Too heavy for demo scope; replaced with event-driven EventBridge pattern                 |
| PostgreSQL for metrics              | AI proposed PostgreSQL for metrics storage   | **Rejected**   | Replaced with S3 audit logs + REST metrics API, eliminating database dependency entirely |
| Prometheus for metrics              | AI proposed Prometheus exporter              | **Changed**    | Used REST API metrics endpoint for simplicity; Prometheus would be a production upgrade  |
| Hardcoded secrets in docker-compose | AI placed credentials inline                 | **Changed**    | Moved to environment variables with `.env` file support, added `.env` to `.gitignore`    |
| Single Terraform workspace          | AI proposed single tfvars file               | **Changed**    | Split into three environments with module isolation — cleaner separation                 |
| Full Step Functions Live            | AI suggested running actual AWS SFN locally  | **Rejected**   | Not possible without AWS; replaced with single S3 Event Router Lambda                    |
| No health checks on containers      | AI omitted health checks                     | **Changed**    | Added health checks to all services for bootstrap reliability                            |

## Validation Process

All AI-generated code was validated through:

1. **Static analysis:** Python files reviewed for syntax errors, type consistency, and import correctness
2. **Schema validation:** Terraform files validated with `terraform fmt` and `terraform validate`
3. **Logic review:** Pipeline execution paths traced through the S3 Event Router Lambda
4. **Integration testing:** Docker Compose stack built and run with `docker compose up`
5. **API testing:** curl commands executed against the S3 Event Router to verify file processing, routing, and audit logging
6. **Grafana testing:** Dashboard loaded in Grafana to verify panel data sources and Infinity REST queries
7. **MinIO verification:** Bucket contents inspected after processing to confirm correct routing to good/quarantine/audit buckets

## Key AI Principles Applied

- **AI as a tool, not a replacement for reasoning:** Every AI-generated block was reviewed for correctness, security, and appropriateness
- **Prefer simplicity:** When AI proposed complex solutions, simpler alternatives (event-driven vs cron, S3 audit logs vs metrics database) were preferred
- **Security-first:** AI-generated credentials and configurations were audited for hardcoded secrets, public access, and least-privilege violations
- **Context matters:** AI did not have context on the local-first requirement, so its cloud-oriented suggestions were adapted or rejected accordingly

## Self-Critique

**What could have been done better:**

- More rigorous integration tests between all components (router → audit → metrics data flow)
- Load testing to validate S3 audit log querying performance under high file volume
- Earlier validation of Grafana Infinity datasource queries before committing the dashboard JSON
- Automated end-to-end test script for the complete pipeline
