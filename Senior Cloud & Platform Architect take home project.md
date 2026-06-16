# Senior Architect Take-Home Assignment

## Overview

Build a small, secure, reproducible data platform that ingests partner files across multiple environments.

The goal is not to recreate our full production platform. The goal is to show how you think about infrastructure, orchestration, security, failure handling, and reproducibility when building a production-shaped system.

You may use AI tools. If you do, include a short disclosure describing where AI helped, what you accepted unchanged, what you changed or rejected, and how you validated AI-generated output.

## Scenario

An external partner delivers CSV files daily. Your task is to build a standalone mini-platform that can:

1. provision its runtime with Terraform,
2. orchestrate processing with Airflow or a close equivalent,
3. validate incoming files,
4. route invalid files safely,
5. process valid files into a downstream output,
6. expose operational visibility through Grafana,
7. support `dev`, `test`, and `prod` environments,
8. be reproduced by another engineer from your documentation.

The project should be runnable by a reviewer on their own machine without access to your personal cloud account.

## Timebox

Target effort is 6 to 8 hours. We are not looking for production completeness. We are looking for judgment, tradeoffs, and execution quality within constraints.

## Required Deliverables

Provide a repository containing the following:

1. Infrastructure as code for the mini-platform.
2. A working orchestrated workflow.
3. Sample input data, including at least one valid file and one invalid file.
4. Application or workflow code needed to validate and process the files.
5. A `README.md` with setup, run, validation, and teardown instructions.
6. A short architecture note describing key design decisions.
7. A short operations note describing failure handling, reruns, and observability.
8. A Grafana dashboard definition, screenshot, or export that a reviewer can load or inspect.
9. A short AI usage note.

## Functional Requirements

Your solution must:

1. support three environments: `dev`, `test`, and `prod`,
2. isolate environment-specific configuration cleanly,
3. ingest files from an S3-compatible location or an equivalent object-store abstraction,
4. validate file structure before downstream processing,
5. quarantine, archive, or otherwise isolate invalid files,
6. process valid files into a downstream artifact such as a cleaned file, database table, or summarized output,
7. publish enough telemetry for a reviewer to understand system behavior,
8. expose that telemetry in Grafana,
9. provide a safe rerun or replay story,
10. include at least one deliberate failure scenario and show the expected recovery path,
11. include at least one selective execution or selective deployment mechanism.

## Technical Constraints

Design the project so that we can reproduce it locally. You may use cloud services optionally, but the core evaluation path must not depend on access to your AWS account.

Your solution should include:

1. Terraform for environment-aware infrastructure or runtime configuration.
2. Airflow, or a closely similar orchestrator if you believe a substitution is justified.
3. Secure handling of secrets and configuration. Do not hardcode secrets into source files.
4. Grafana as the primary visualization surface for operational behavior.
5. At least one explicit network, trust-boundary, or isolation decision and an explanation of the tradeoff.
6. A one-command or low-friction bootstrap path.

The Grafana component does not need to be enterprise-grade. It does need to be meaningful. At minimum, a reviewer should be able to inspect a dashboard that shows recent workflow runs, success or failure counts, and at least one signal related to invalid file handling or processing latency.

## Suggested Scope

We recommend a local-first stack such as Docker plus locally reproducible supporting services. You may decide the exact stack.

Examples of reasonable downstream outputs include:

1. a normalized CSV,
2. a table in a local database,
3. a generated summary file,
4. a load-ready artifact for a downstream consumer.

Examples of selective behavior include:

1. running only workflows impacted by a changed config,
2. targeting a single environment,
3. selectively processing changed partner feeds,
4. selectively applying part of the Terraform footprint.

Examples of acceptable Grafana signals include:

1. workflow success and failure counts,
2. files processed by type or environment,
3. invalid file counts,
4. run duration or queue delay,
5. environment-specific health indicators.

## Non-Goals

You do not need to:

1. reproduce a full enterprise data platform,
2. implement real business-specific claims logic,
3. use our production AWS accounts,
4. build a large UI,
5. optimize for scale beyond the demo scenario.

## Submission Expectations

Please include:

1. clear assumptions,
2. known limitations,
3. what you would do next with more time,
4. exact reviewer steps to reproduce the result,
5. any credentials or secrets setup that must occur before running the project,
6. how Grafana should be accessed and what the reviewer should look at,
7. how AI was used and how AI-generated output was validated.

If your project requires manual setup steps, keep them minimal and explain why they were necessary.

## Evaluation Criteria

We will evaluate:

1. architecture quality,
2. reproducibility,
3. security posture,
4. operational maturity,
5. usefulness of the Grafana observability layer,
6. correctness of the workflow,
7. clarity of tradeoffs,
8. quality of AI use and engineering judgment.

## What Strong Submissions Usually Show

Strong submissions usually:

1. are easy to run from the documentation,
2. make deliberate scope decisions,
3. show clean separation between environments,
4. treat failure paths as first-class behavior,
5. expose meaningful operational visibility in Grafana,
6. explain security and trust boundaries clearly,
7. use AI as a tool rather than a substitute for reasoning.

## What Weak Submissions Usually Show

Weak submissions usually:

1. are hard to reproduce,
2. hide complexity behind incomplete documentation,
3. hardcode sensitive configuration,
4. skip failure handling,
5. add Grafana only as decoration rather than as a useful operational surface,
6. build many pieces shallowly rather than a few pieces well,
7. cannot explain why the design was chosen.

## Submission Format

Please submit a repository link or an archive containing the full project.

Your repository should include these top-level documents:

1. `README.md`
2. `ARCHITECTURE.md`
3. `OPERATIONS.md`
4. `AI_USAGE.md`
5. `GRAFANA.md` or equivalent dashboard notes

Optional extras are welcome if they improve reproducibility or explainability, but they are not required. If there is any ambiguity, you have the liberty to make assumptions as far as they are explained in the documentation.
