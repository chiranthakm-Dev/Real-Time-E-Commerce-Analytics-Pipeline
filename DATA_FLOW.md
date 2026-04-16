# Data Flow Documentation

## Event Lifecycle: From Click to Dashboard

### Timeline Overview

```
T+0ms    ─ User clicks "Buy Now" on product page
T+1ms    ─ Event generated with UUID, timestamp, category
T+2ms    ─ Producer serializes to JSON, publishes to Kafka topic
T+10ms   ─ Message arrives at Redpanda broker partition
T+20ms   ─ Consumer polls message from Kafka
T+25ms   ─ Pydantic validates event schema
T+30ms   ─ Event inserted into PostgreSQL raw_events table
T+60s    ─ dbt runs transformation models (hourly schedule or manual)
T+75s    ─ Anomaly detector polls last 500 purchases, flags if needed
T+80s    ─ Grafana dashboard refreshes (5s polling interval)
T+90s    ─ Dashboard shows updated revenue, anomalies, dbt test results
         └─ Total latency from click to visualization: 90 seconds (acceptable for near-real-time)
```

---

## Detailed Event Flow

### Example: Purchase Event

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "usr_4821",
  "session_id": "sess_9911",
  "product_id": "prod_001",
  "category": "clothing",
  "revenue": 49.99,
  "currency": "EUR",
  "ts": "2026-04-16T14:23:11Z",
  "country": "NL"
}
```

### Layer 1: Producer (src/producer/main.py)

```
Step 1: Generate Realistic Data
  - User ID: faker.random_int(1, 10000) → "usr_4821"
  - Category: random.choice(['electronics', 'clothing', ...])
  - Revenue: faker.pyfloat(left_digits=2, right_digits=2, positive=True)
  - Timestamp: datetime.utcnow().isoformat()

Step 2: Inject Anomaly (1/200 events)
  - If random() < 0.005:
      revenue *= 10  # Fraud simulation
      logger.warning(f"ANOMALY INJECTED: {event_id}")

Step 3: Serialize & Publish
  - Serialize to JSON bytes
  - kafka_producer.send(
      topic='purchases',
      key=user_id.encode(),  # Route by user
      value=json.dumps(event).encode()
    )

Step 4: Verify
  - Callback on_delivery() confirms broker receipt
```

### Layer 2: Kafka Broker (Redpanda)

```
Step 1: Receive Message
  - Topic: 'purchases'
  - Partition: hash(user_id) % 2  (partitioned by user for session ordering)
  - Offset: auto-incremented within partition

Step 2: Replicate
  - Write to disk (durable)
  - Hold in memory for fast consumer retrieval

Step 3: Wait for Consumer
  - Consumer group 'ecommerce-consumer-group' subscribes
  - Broker assigns partitions to consumer instances
  - Message stays in topic for 1 hour (retention policy)
```

### Layer 3: Consumer (src/consumer/main.py)

```
Step 1: Poll Kafka
  consumer.poll(timeout_ms=1000, max_records=500)
  → Returns list of messages (batch for efficiency)

Step 2: Deserialize
  for message in messages:
      event_dict = json.loads(message.value.decode())

Step 3: Validate (Pydantic)
  try:
      event = PurchaseEvent(**event_dict)  # Raises ValidationError on invalid
  except ValidationError as e:
      # Log to dead_letter table
      dead_letter_handler.log(message, str(e), "validation_error")
      consumer.commit()  # Still advance offset (don't get stuck)
      continue

Step 4: Insert Idempotently
  cursor.execute("""
      INSERT INTO raw_events (event_id, user_id, ...) 
      VALUES (%s, %s, ...)
      ON CONFLICT (event_id) DO NOTHING
  """, event_tuple)
  connection.commit()

Step 5: Commit Offset
  consumer.commit()  # Only after successful DB insert
  # On next restart, consumer resumes from this offset
```

### Layer 4: Transformation (dbt)

```
Step 1: Schedule dbt run (Hourly or manual)
  dbt run --select tag:mart  # Transform only marts

Step 2: Execute Staging Models
  stg_purchases.sql:
    - Casts raw_events → typed columns
    - Filters out test events
    - Ensures data integrity

Step 3: Execute Mart Models
  fct_purchases.sql:
    - Joins stg_purchases with dim_users
    - Adds computed columns (day_of_week, hour, etc.)
    - Flags anomalies based on revenue thresholds

Step 4: Execute Tests
  dbt test:
    - Unique test on event_id
    - Not null on revenue
    - Revenue in (0, 10000)
    - Country in accepted list

Step 5: On-Run-End Hook
  if test_failures > 0:
      send_slack_webhook("⚠️ dbt tests failed")

Step 6: Update Timestamps
  All models update dbt_loaded_at = NOW()
  Dashboard can query "last dbt run was X minutes ago"
```

### Layer 5: Anomaly Detection (src/anomaly_detection/detector.py)

```
Step 1: Polling Trigger (every 60 seconds)
  while True:
      sleep(60)
      # Continue to next step

Step 2: Fetch Recent Purchases
  SELECT * FROM fct_purchases 
  WHERE event_ts > NOW() - INTERVAL '12 hours'
  ORDER BY event_ts DESC LIMIT 500

Step 3: Compute Features
  For each purchase:
    - revenue_normalized = (revenue - mean) / std_dev
    - hour_of_day = event_ts.hour
    - events_in_session = count(events in this session_id)
    - time_since_last_purchase_seconds = now - prev_event.ts

Step 4: Load Trained Model
  model = load_model_from_db(latest_version)

Step 5: Predict
  predictions = model.predict(features_array)  # Array of -1 or 1
  anomaly_scores = model.score_samples(features_array)  # Continuous scores

Step 6: Log Anomalies
  for score, prediction in zip(anomaly_scores, predictions):
      if prediction == -1:  # Anomaly
          INSERT INTO anomalies(
              event_id, anomaly_score, detected_at, model_version
          ) VALUES (...)

Step 7: Export Metrics
  anomaly_count_total += count(anomalies)
  prometheus_client.expose_metrics()  # Available at /metrics
```

### Layer 6: Dashboard (Grafana)

```
Step 1: Datasource Connection
  Grafana → PostgreSQL connection established on startup
  Via provisioning/datasources/postgres.yml

Step 2: Panel 1 - Conversion Funnel Query
  Query the events table:
    - Distinct sessions with page_views
    - Distinct sessions with cart_adds
    - Distinct sessions with purchases
    - Calculate percentages

Step 3: Panel 2 - Revenue Time Series
  Query fct_purchases:
    - Group by DATE_TRUNC('hour', event_ts)
    - SUM(revenue) by category
    - Overlay anomalies as red annotations

Step 4: Panel 3 - Cohort Retention
  Query dim_users + fct_purchases:
    - Bucket by first_purchase_week
    - Calculate % returning each week

Step 5: Panel 4 - Data Quality
  Query dbt test results:
    - If "not_null" test on revenue: PASS ✓
    - If "accepted_values" test on country: FAIL ✗
    - Show as red/green table rows

Step 6: Auto-Refresh
  Dashboard polls PostgreSQL every 5 seconds
  Grafana re-renders charts
  (User sees live updates)
```

---

## Data Lineage

```
Kafka Topics (raw)
│
├─ page_views → stg_page_views → fct_conversion_funnel
├─ cart_events → stg_cart_events → fct_conversion_funnel
└─ purchases → stg_purchases ─┬─ fct_purchases → daily_revenue
                               │
                               └─ anomaly_detection ─→ anomalies table
                                                        ↓
                                                    prometheus_metrics
                                                        ↓
                                                    grafana_annotations
```

---

## Failure Scenarios & Recovery

### Scenario 1: Consumer Crashes After Processing, Before Offset Commit

```
Timeline:
  T+30ms  - Event inserted into raw_events (committed to DB)
  T+32ms  - consumer.commit() starts (async call)
  T+33ms  - ⚠️ Consumer process crashes (OOM, SIGKILL, etc.)
  
Recovery:
  T+35s   - Consumer restarts (Docker restart policy)
  T+40s   - Rejoins consumer group
  T+45s   - Kafka rebalances
  T+50s   - Consumer resumes from LAST COMMITTED offset
           (because offset commit never completed at T+32ms)
  T+55s   - Same message redelivered from Kafka
  T+60ms  - INSERT ... ON CONFLICT (event_id) DO NOTHING
           (Duplicate silently ignored)
  ✓ Result: No data loss, no duplication
```

### Scenario 2: Event Fails Validation

```
Timeline:
  T+25ms  - Event arrives at consumer
  T+26ms  - Pydantic validation fails (revenue > 10000)
  
Handling:
  T+27ms  - Insert into dead_letter table with error reason
  T+28ms  - consumer.commit() (advance offset despite failure)
  T+30ms  - Log to stderr for ops visibility
  
Result:
  ✓ Event not silently lost
  ✓ Error is inspectable (dead_letter table)
  ✓ Consumer doesn't get stuck on bad event
```

### Scenario 3: dbt Test Fails

```
Timeline:
  T+60s   - dbt run completes
  T+61s   - dbt test runs
  T+62s   - ✗ Test fails: fct_purchases.revenue has nulls
  
Handling:
  T+63s   - on-run-end hook triggers
  T+64s   - Send Slack webhook: "@data-eng ⚠️ dbt test failed"
  T+65s   - Ops receives alert
  T+120s  - Ops investigates dead_letter table
           Finds: raw event with missing revenue field
  T+125s  - Decision: Update data source, re-run dbt
           OR: Investigate upstream producer bug
  
Result:
  ✓ Issue caught automatically
  ✓ Optic visibility (Slack)
  ✓ Traceability (dead_letter + dbt logs)
```

### Scenario 4: Model Drift (Anomaly Detector False Positives)

```
Timeline:
  Week 1  - Model trained on baseline purchase patterns
           Contamination = 1% (expect 1% anomalies)
  Week 2  - Sales spike (holiday season)
           Model flags 5% of events as anomalies (5x false positive rate)
  
Detection:
  Weekly report shows: precision = 0.2, recall = 0.9
  (Too many false positives)
  
Mitigation:
  Option 1: Lower contamination to 0.1% (less aggressive)
  Option 2: Retrain on Week 2 data (adapt to new distribution)
  Option 3: Inspect feature drift (time_since_last_purchase changed)
  
Action:
  - Retrain model
  - Update model_registry with new version
  - Anomaly detector automatically uses latest version
```

---

## Capacity Planning

### Events/Second Estimates

| Scenario | Page Views/s | Cart Events/s | Purchases/s | Total |
|----------|--------------|---------------|-------------|-------|
| Light traffic | 100 | 50 | 50 | 200 |
| Normal traffic | 200 | 100 | 100 | 400 |
| Peak traffic | 350 | 175 | 175 | 700 |

**Current capacity:** 500 events/sec sustained ✅

### Database Growth

| Period | Raw Events | Models | Total Size |
|--------|-----------|--------|-----------|
| 1 day | 43.2M rows | 15 GB | 18 GB |
| 7 days | 302.4M rows | 100 GB | 120 GB |
| 30 days | 1.3B rows | 450 GB | 500 GB |

**Mitigation:**
- Partitioned tables by date (monthly partitions)
- Retention policy: Keep raw_events for 30 days, archive to S3
- Aggregate daily_revenue for long-term analysis

---

## Monitoring Checklist

### Daily
- [ ] Check Grafana dashboard loads (http://localhost:3000)
- [ ] Verify revenue trend is reasonable
- [ ] Check anomaly_count_total in Prometheus (should be < 2% of events)
- [ ] Review dbt test results (all should be green)

### Weekly
- [ ] Anomaly model retraining completed
- [ ] Model performance metrics stable
- [ ] Dead-letter queue < 0.1% of total events
- [ ] Consumer lag < 5 seconds

### Monthly
- [ ] Review data retention and archive old events
- [ ] Analyze cohort retention trends
- [ ] Performance review: throughput, latency, resource usage
- [ ] Update README with new insights

---

## Integration Points

### Slack Alerts
```python
# On dbt test failure
POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL
{
    "text": "⚠️ dbt test failed",
    "attachments": [{
        "color": "danger",
        "fields": [
            {"title": "Test", "value": "fct_purchases.revenue > 0"},
            {"title": "Failed rows", "value": "3"},
            {"title": "Run ID", "value": "abc123"}
        ]
    }]
}
```

### Prometheus Scrape
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'anomaly-detector'
    static_configs:
      - targets: ['anomaly-detector:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Grafana Provisioning
```yaml
# grafana/provisioning/datasources/postgres.yml
datasources:
  - name: PostgreSQL
    type: postgres
    url: postgres:5432
    database: analytics
    user: postgres
    secureJsonData:
      password: postgres
```

---

## Performance Tuning Guide

### Consumer Lag Growing?
1. Increase `max.poll.records` from 500 to 1000
2. Increase consumer instance count (horizontal scaling)
3. Profile database inserts: check for lock contention

### dbt Run Taking > 5 Minutes?
1. Check query plans: `EXPLAIN ANALYZE` on slow models
2. Add indexes on join columns (user_id, product_id, event_ts)
3. Consider materializing intermediate results

### Anomaly Detection Lagging Behind?
1. Increase polling frequency from 60s to 30s
2. Reduce feature window from 500 to 200 purchases (faster computation)
3. Cache model in memory (reload only if version changes)

### Dashboard Slow?
1. Query too slow? Check Grafana query performance panel
2. Add materialized views for expensive aggregations
3. Cache query results in Redis (if volumes justify)

