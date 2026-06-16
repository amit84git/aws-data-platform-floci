# AI Usage Disclosure

## Overview

This project was developed with assistance from Cline (an AI coding assistant). Below is a transparent account of how AI was used, what was accepted unchanged, what was changed or rejected, and how the output was validated.

## How AI Was Used

| Task                                                         | AI Role                                            | Human Role                                                                                       |
| ------------------------------------------------------------ | -------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Project scaffolding                                          | Generated initial file structure from requirements | Reviewed structure, adjusted naming, added missing directories                                   |
| Docker Compose configuration                                 | Drafted service definitions based on requirements  | Validated port mappings, added health checks, adjusted volume mounts                             |
| Python engine code (`engine/main.py`, `engine/db.py`, etc.)  | Generated initial implementations from spec        | Added error handling, input validation, logging; adjusted async patterns                         |
| Lambda functions (validator, processor, quarantine, metrics) | Generated core validation/processing logic         | Extended validation rules, added edge case handling, enriched quarantine manifests               |
| Terraform configurations                                     | Generated module and environment files             | Added security blocks (public_access_block), versioning, lifecycle policies, IAM least-privilege |
| Grafana dashboard JSON                                       | Generated initial panel structure and SQL queries  | Adjusted panel sizing, added annotations, validated SQL against actual DB schema                 |
| Documentation (README, ARCHITECTURE, OPERATIONS, GRAFANA)    | Generated initial drafts from structured prompts   | Reviewed for accuracy, added missing details, adjusted tone for technical audience               |

## What Was Accepted Unchanged

- **Boilerplate code** (Docker Compose service shells, Terraform resource stubs, Python `__init__.py` files)
- **SQL queries** for Grafana panels — validated against the actual metrics database schema
- **ASL state machine definition** structure — standard AWS Step Functions format
- **Sample data CSV files** — simple format, validated by the validator Lambda

## What Was Changed or Rejected

| Item                                | AI Output                                    | Final Decision | Reason                                                                                                         |
| ----------------------------------- | -------------------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------- |
| Airflow-based orchestration         | AI proposed using Airflow with LocalExecutor | **Rejected**   | Too heavy for demo scope; built FloCI Engine instead (100 lines vs Airflow's 2GB+ footprint)                   |
| MongoDB for state storage           | AI proposed MongoDB for flexibility          | **Rejected**   | Added unnecessary complexity; PostgreSQL with SQLAlchemy provides schema enforcement and simpler setup         |
| Prometheus for metrics              | AI proposed Prometheus exporter              | **Changed**    | Used PostgreSQL for simplicity; Grafana reads directly from metrics DB. Prometheus would be production upgrade |
| Hardcoded secrets in docker-compose | AI placed credentials inline                 | **Changed**    | Moved to environment variables with `.env` file support, added `.env` to `.gitignore`                          |
| Single Terraform workspace          | AI proposed single tfvars file               | **Changed**    | Split into three environments with module isolation — cleaner separation                                       |
| Full Step Functions Live            | AI suggested running actual AWS SFN locally  | **Rejected**   | Not possible without AWS; built `StateMachineRunner` for ASL execution                                         |
| No health checks on containers      | AI omitted health checks                     | **Changed**    | Added health checks to all services for bootstrap reliability                                                  |

## Validation Process

All AI-generated code was validated through:

1. **Static analysis:** Python files reviewed for syntax errors, type consistency, and import correctness
2. **Schema validation:** Terraform files validated with `terraform fmt` and `terraform validate`
3. **Logic review:** Workflow execution paths traced through the state machine definition
4. **Integration testing:** Docker Compose stack built and run with `docker compose up`
5. **API testing:** curl commands executed against the running FloCI Engine to verify workflow creation, execution, and metrics
6. **Grafana testing:** Dashboard loaded in Grafana to verify panel data sources and SQL queries
7. **Replay testing:** `scripts/replay.sh` tested with quarantined files

## Key AI Principles Applied

- **AI as a tool, not a replacement for reasoning:** Every AI-generated block was reviewed for correctness, security, and appropriateness
- **Prefer simplicity:** When AI proposed complex solutions, simpler alternatives (FloCI Engine vs Airflow, PostgreSQL vs MongoDB) were preferred
- **Security-first:** AI-generated credentials and configurations were audited for hardcoded secrets, public access, and least-privilege violations
- **Context matters:** AI did not have context on the local-first requirement, so its cloud-oriented suggestions were adapted or rejected accordingly

## Self-Critique

**What could have been done better:**

- More rigorous integration tests between all components (validator → processor → metrics data flow)
- Load testing to validate PostgreSQL performance for metrics under high workflow volume
- Earlier validation of Grafana SQL queries before committing the dashboard JSON
