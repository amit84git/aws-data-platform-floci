# Grafana Dashboard Notes

## Access

1. Start the FloCI platform: `./scripts/bootstrap.sh`
2. Open Grafana: http://localhost:3000
3. Login: `admin / admin` (you'll be prompted to change password on first login — can skip)
4. Navigate to: **Dashboards > FloCI > FloCI Partner Ingestion Dashboard**

## Dashboard: FloCI Partner Ingestion Dashboard

The dashboard is **auto-provisioned** — it will appear automatically after Grafana starts. Provisioning files are at:

```
grafana/dashboards/ingestion-dashboard.json   # Dashboard definition
grafana/dashboards/dashboard.yml               # Dashboard provider config
grafana/datasources/datasource.yml              # PostgreSQL datasource
```

## Panels

| #   | Panel                        | Type        | Data Source   | SQL Query                                                                                                                       |
| --- | ---------------------------- | ----------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Workflow Runs (Last 24h)** | Stat        | FloCI Metrics | `SELECT COUNT(*) FROM workflow_metrics WHERE event_type = 'workflow_completed' AND created_at > NOW() - INTERVAL '24 hours'`    |
| 2   | **Successful Runs**          | Stat        | FloCI Metrics | `SELECT COUNT(*) FROM workflow_metrics WHERE event_type = 'workflow_completed' AND event_data->>'status' = 'success'`           |
| 3   | **Failed Runs**              | Stat        | FloCI Metrics | `SELECT COUNT(*) FROM workflow_metrics WHERE event_type = 'workflow_completed' AND event_data->>'status' = 'failed'`            |
| 4   | **Files Processed by Env**   | Bar Chart   | FloCI Metrics | `SELECT environment, COUNT(*) FROM workflow_metrics WHERE event_type = 'file_processed' GROUP BY environment`                   |
| 5   | **Invalid Files by Env**     | Bar Chart   | FloCI Metrics | `SELECT environment, COUNT(*) FROM workflow_metrics WHERE event_type = 'file_invalid' GROUP BY environment`                     |
| 6   | **Workflow Runs Timeline**   | Time Series | FloCI Metrics | `SELECT DATE_TRUNC('minute', created_at), COUNT(*) FROM workflow_metrics WHERE event_type = 'workflow_completed' GROUP BY time` |
| 7   | **Processing Errors**        | Table       | FloCI Metrics | `SELECT created_at, event_data->>'file', event_data->>'errors' FROM workflow_metrics WHERE event_type = 'file_invalid'`         |

## Filters

- **Environment filter** (top of dashboard): Select `dev`, `test`, `prod`, or `All` to scope the dashboard.

## Annotations

- **Workflow Errors**: Automatically annotate the timeline when `file_error` events occur.

## Expected Behavior

After bootstrapping and triggering a few workflow runs, you should see:

1. **Stat panels** showing 3+ workflow runs (one per environment if the scheduler ran).
2. **Bar charts** showing files processed and invalid files broken down by environment.
3. **Timeline** showing the workflow execution cadence.
4. **Error table** listing the specific validation errors from `bad_data.csv`.

## Generating More Data

To see a more populated dashboard, trigger multiple workflow runs:

```bash
for i in {1..5}; do
  curl -X POST http://localhost:8080/api/v1/workflows \
    -H "Content-Type: application/json" \
    -d '{"name":"load-test","environment":"dev","start_immediately":true}'
  sleep 2
done
```

## Troubleshooting

| Problem                   | Likely Cause                    | Solution                                                    |
| ------------------------- | ------------------------------- | ----------------------------------------------------------- |
| Dashboard not appearing   | Grafana provisioning not loaded | Wait 30s for auto-provisioning, or restart Grafana          |
| "Datasource not found"    | Datasource provisioning failed  | Check `grafana/datasources/datasource.yml`, restart Grafana |
| Empty panels              | No metrics recorded yet         | Trigger a workflow and wait for execution                   |
| "relation does not exist" | Metrics DB not initialized      | Run `./scripts/bootstrap.sh` to create tables               |

## Production Considerations

- **Replace PostgreSQL source** with Prometheus for time-series optimization
- **Add alerting rules** in Grafana for workflow failure rate >5%
- **Extend retention** with data source `max_retention_days` setting
- **Add dashboard permissions** for team-based access control
- **Export dashboard JSON** to version control for declarative management
