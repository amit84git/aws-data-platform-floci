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
grafana/datasources/datasource.yml              # S3/Infinity datasource config
```

## How It Works (No PostgreSQL)

The dashboard no longer uses PostgreSQL. Instead:

1. **Metrics API endpoint:** The S3 Event Router (`floci-s3-event-router`) exposes `GET /api/v1/metrics` which aggregates audit logs from MinIO's `ingestion-audit` S3 bucket.
2. **Infinity datasource plugin:** Grafana uses the Infinity datasource to query the REST API endpoint and render panels from the returned JSON.
3. **Immutable audit logs:** All pipeline events are recorded as structured JSON in S3. The metrics API reads these logs and returns pre-aggregated counts.

This eliminates the need for a metrics database entirely — consistent with FloCI's no-PostgreSQL architecture.

## Panels

| #   | Panel                        | Type        | Data Source           | Query Method                                |
| --- | ---------------------------- | ----------- | --------------------- | ------------------------------------------- |
| 1   | **Total Pipeline Events**    | Stat        | FloCI Audit Logs (S3) | `$.total_events` from `/api/v1/metrics`     |
| 2   | **Good Files Routed**        | Stat        | FloCI Audit Logs (S3) | `$.good_files` from `/api/v1/metrics`       |
| 3   | **Quarantined Files**        | Stat        | FloCI Audit Logs (S3) | `$.quarantine_files` from `/api/v1/metrics` |
| 4   | **Events by Type**           | Bar Chart   | FloCI Audit Logs (S3) | `$.events_by_type` from `/api/v1/metrics`   |
| 5   | **Errors (Last 24h)**        | Stat        | FloCI Audit Logs (S3) | `$.errors` from `/api/v1/metrics`           |
| 6   | **Pipeline Events Timeline** | Time Series | FloCI Audit Logs (S3) | `$.events_timeline` from `/api/v1/metrics`  |
| 7   | **Recent Audit Logs**        | Table       | FloCI Audit Logs (S3) | `$` (full response) from `/api/v1/metrics`  |

## Expected Behavior

After bootstrapping and triggering a few file uploads (sample data is auto-seeded), you should see:

1. **Stat panels** showing counts of total pipeline events, good files routed, quarantined files, and errors.
2. **Bar chart** showing event types broken down by category.
3. **Timeline** showing the event cadence over the last 24 hours.
4. **Table** showing aggregated pipeline metrics at a glance.

## Generating More Data

To see a more populated dashboard, trigger multiple file uploads:

```bash
for i in {1..5}; do
  curl -X POST http://localhost:8081/api/v1/process-event \
    -H "Content-Type: application/json" \
    -d '{"file_key":"load_test_'$i'.csv","content":"partner_id,date,amount,currency\n1,2026-01-01,100,USD"}'
  sleep 2
done
```

## Troubleshooting

| Problem                  | Likely Cause                    | Solution                                                                                |
| ------------------------ | ------------------------------- | --------------------------------------------------------------------------------------- |
| Dashboard not appearing  | Grafana provisioning not loaded | Wait 30s for auto-provisioning, or restart Grafana                                      |
| "Datasource not found"   | Infinity plugin not installed   | Check `GF_INSTALL_PLUGINS` includes `yesoreyeram-infinity-datasource` in docker-compose |
| Empty panels             | No pipeline events recorded yet | Upload a file to MinIO or trigger via API                                               |
| "Plugin not found" error | Infinity plugin didn't install  | Restart Grafana, check logs: `docker logs floci-grafana`                                |
| All panels show 0        | Audit logs not yet created      | Check MinIO console at http://localhost:9001 for `ingestion-audit` bucket contents      |

## Production Considerations

- **Replace REST API polling** with Prometheus for real-time time-series metrics
- **Add alerting rules** in Grafana for quarantine failure rate >5%
- **Use Athena or S3 Select** for large-scale audit log querying instead of the in-memory API aggregation
- **Add dashboard permissions** for team-based access control
- **Export dashboard JSON** to version control for declarative management
