# Implementation Roadmap

This document outlines the step-by-step implementation plan for building the Real-Time E-Commerce Analytics Pipeline.

---

## Phase 0: Project Setup (2-4 hours)

### 0.1 Repository & Environment
- [ ] Initialize Git repo
- [ ] Create `.gitignore` (Python, Docker, IDE files)
- [ ] Create `.env.example` (no secrets; template only)
- [ ] Create `docker-compose.yml` structure (empty services)

**Files to create:**
```
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
└── docs/
    ├── ARCHITECTURE.md
    ├── DATA_FLOW.md
    ├── GETTING_STARTED.md
    └── ADRs/
```

### 0.2 Docker Infrastructure
- [ ] Create `Dockerfile` for Python services (producer, consumer, anomaly detection)
- [ ] Create `postgres/init.sql` (database schema)
- [ ] Create `redpanda/docker-compose-partial.yml` reference
- [ ] Add health checks to all services

---

## Phase 1: Event Pipeline (3-4 days)

### 1.1 Kafka/Redpanda Setup
- [ ] Add Redpanda service to docker-compose.yml
- [ ] Create 3 Kafka topics:
  - `page_views` (2 partitions)
  - `cart_events` (2 partitions)
  - `purchases` (2 partitions)
- [ ] Set retention to 1 hour
- [ ] Configure consumer group offset reset to `earliest`

**Expected outcome:** `docker compose up` starts Redpanda, topics visible in rpk CLI

### 1.2 Event Producer
- [ ] Create `src/producer/main.py`
- [ ] Create `src/producer/schemas.py` (event definitions)
- [ ] Create `src/producer/anomaly_injector.py`
- [ ] Install dependencies: `faker`, `confluent-kafka`
- [ ] Implement:
  - Generate page_view events (200/sec)
  - Generate cart_events (150/sec)
  - Generate purchase events (150/sec)
  - Inject anomalies every ~200 & ~500 events
  - Publish to Kafka with correct partition key (`user_id`)

**Features:**
- Configurable throughput (env variable)
- Event ID as UUID
- Timestamp as ISO 8601
- Anomaly injection rate logged

**Expected outcome:** Producer publishes 500 events/sec to Kafka

### 1.3 PostgreSQL Setup
- [ ] Create `postgres/init.sql`:
  - `raw_events` table (immutable, append-only)
  - `dead_letter` table (validation failures)
  - Indexes on `event_id`, `user_id`, `ts`
- [ ] Add PostgreSQL service to docker-compose.yml
- [ ] Set up volume for persistence

**Schema:**
```sql
CREATE TABLE raw_events (
    event_id UUID PRIMARY KEY,
    user_id VARCHAR(50),
    session_id VARCHAR(50),
    product_id VARCHAR(50),
    category VARCHAR(100),
    revenue DECIMAL(10, 2),
    currency VARCHAR(3),
    ts TIMESTAMP,
    country VARCHAR(2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE dead_letter (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID,
    raw_payload JSONB,
    error_reason TEXT,
    error_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Phase 2: Consumer & Validation (2-3 days)

### 2.1 Consumer Foundation
- [ ] Create `src/consumer/main.py`
- [ ] Create `src/consumer/models.py` (Pydantic schemas)
- [ ] Create `src/consumer/database.py` (connection pooling)
- [ ] Install dependencies: `confluent-kafka`, `pydantic`, `psycopg2`

**Consumer loop:**
```python
for message in kafka_consumer.poll():
    try:
        event = PurchaseEvent(**json.loads(message))
        db.insert(event)  # idempotent
        kafka_consumer.commit()
    except ValidationError as e:
        dead_letter_handler.log(message, str(e))
        kafka_consumer.commit()  # Still advance offset
```

### 2.2 Pydantic Validation
- [ ] Create `PurchaseEvent` model with validators:
  - `revenue` > 0 and < 10,000
  - `country` in accepted list
  - `ts` not in future
  - `ts` not older than 24 hours
  - `user_id` format validation (regex)

**Expected outcome:** Invalid events logged to dead_letter, consumer continues

### 2.3 Idempotent Insert Pattern
- [ ] Implement `INSERT ... ON CONFLICT (event_id) DO NOTHING` in `database.py`
- [ ] Test consumer restart safety:
  - Crash consumer after insert, before offset commit
  - Restart consumer
  - Verify no duplication in database

**Expected outcome:** Duplicate events silently ignored; data integrity maintained

### 2.4 Integration
- [ ] Add consumer service to docker-compose.yml
- [ ] Verify: `docker compose up` → data flows from Kafka to PostgreSQL

---

## Phase 3: Data Transformation with dbt (3-4 days)

### 3.1 dbt Project Structure
- [ ] Initialize dbt project: `dbt init`
- [ ] Create `dbt/profiles.yml` (PostgreSQL connection)
- [ ] Create directory structure:
  ```
  dbt/
  ├── models/
  │   ├── staging/
  │   ├── marts/
  │   └── metrics/
  ├── tests/
  ├── macros/
  ├── schema.yml
  └── dbt_project.yml
  ```

### 3.2 Staging Models
- [ ] Create `stg_page_views.sql`
  - Type casting
  - Rename columns to snake_case
  - Filter test events
- [ ] Create `stg_cart_events.sql` (similar)
- [ ] Create `stg_purchases.sql` (similar)

**Expected outcome:** Models compile with `dbt compile`

### 3.3 Mart Models (Business Logic)
- [ ] Create `fct_purchases.sql`:
  - One row per purchase
  - Join with user dimensions
  - Add computed columns (day_of_week, hour, etc.)
  - Flag anomalies based on revenue
- [ ] Create `dim_users.sql`:
  - User ID, first purchase date, lifetime value
- [ ] Create `fct_conversion_funnel.sql`:
  - Session-level: page views → cart → purchase

**Expected outcome:** Marts materialize with meaningful data

### 3.4 Metrics Layer
- [ ] Create `daily_revenue.sql`:
  - Aggregate by date, category, country
  - Include statistics (count, sum, avg, stddev, min, max)

### 3.5 Comprehensive Testing
- [ ] Add to `schema.yml`:
  - Unique tests on surrogate keys
  - Not-null tests on business keys
  - Expression tests (revenue > 0)
  - Accepted values tests (country in list)
  - Referential integrity tests

**Test examples:**
```yaml
models:
  - name: fct_purchases
    columns:
      - name: event_id
        tests: [unique, not_null]
      - name: revenue
        tests:
          - not_null
          - expression_is_true: "revenue > 0 AND revenue < 1000000"
      - name: country
        tests:
          - accepted_values: ['NL', 'DE', 'FR', 'BE', 'GB']
```

### 3.6 Integration & Scheduling
- [ ] Create `dbt/Dockerfile` (dbt image)
- [ ] Add to docker-compose.yml:
  - dbt run (hourly cron)
  - dbt test (after each run)
- [ ] Create on-run-end hook for Slack alerts

**Expected outcome:** `dbt run && dbt test` → all tests pass

---

## Phase 4: Anomaly Detection (2-3 days)

### 4.1 Isolation Forest Model
- [ ] Create `src/anomaly_detection/detector.py`
- [ ] Install dependencies: `scikit-learn`, `pandas`, `prometheus_client`
- [ ] Implement:
  - Feature engineering (revenue, hour_of_day, session_size, time_since_last)
  - Training on rolling window (last 500 purchases)
  - Prediction loop (every 60 seconds)
  - Anomaly scoring & storage

**Model configuration:**
```python
model = IsolationForest(
    contamination=0.01,  # Expect 1% anomalies
    random_state=42,
    n_estimators=100
)
```

### 4.2 Anomaly Storage
- [ ] Create `anomalies` table in PostgreSQL:
  ```sql
  CREATE TABLE anomalies (
      anomaly_id UUID PRIMARY KEY,
      event_id UUID REFERENCES fct_purchases(event_id),
      anomaly_score FLOAT,
      contamination_fraction FLOAT,
      detected_at TIMESTAMP,
      model_version INT
  );
  ```

### 4.3 Model Registry (MLOps)
- [ ] Create `model_registry` table:
  - Model version
  - Training date
  - Feature set
  - Contamination parameter
  - Accuracy/precision metrics
- [ ] Implement model versioning:
  - Save trained model to BYTEA column
  - Load latest version on startup
  - Track all historical versions

### 4.4 Prometheus Metrics
- [ ] Create `src/anomaly_detection/metrics.py`:
  - Expose `/metrics` HTTP endpoint
  - Counter: `anomaly_count_total`
  - Gauge: `latest_anomaly_score`
- [ ] Add to docker-compose.yml
- [ ] Verify: `curl http://localhost:8000/metrics`

**Expected outcome:** Anomalies detected every 60 seconds; metrics exposed

---

## Phase 5: Grafana Dashboard (2 days)

### 5.1 Datasource Configuration
- [ ] Create `grafana/provisioning/datasources/postgres.yml`:
  - PostgreSQL connection details
  - Database: `analytics`
- [ ] Create `grafana/provisioning/dashboards/dashboard.yml`:
  - Reference to ecommerce_dashboard.json

### 5.2 Dashboard Panels
- [ ] **Panel 1: Conversion Funnel** (Bar Chart)
  - Query: % of sessions reaching each step
  - Data: page_view → cart → purchase

- [ ] **Panel 2: Revenue Over Time** (Line Chart)
  - Query: Hourly revenue by category
  - Overlay: Anomaly annotations (red dots)
  - Time range: Last 24 hours

- [ ] **Panel 3: Cohort Retention Heatmap**
  - Query: Users bucketed by first-purchase week
  - Data: % returning in weeks 1–4

- [ ] **Panel 4: Data Quality** (Table)
  - Query: dbt test results from last run
  - Columns: Test name, Status (green/red)

### 5.3 Auto-Provisioning
- [ ] Create `grafana/provisioning/dashboards/ecommerce_dashboard.json`
- [ ] Export dashboard from Grafana UI (JSON format)
- [ ] Commit to repo
- [ ] Configure Grafana to auto-load on startup

**Expected outcome:** `docker compose up` → Grafana dashboard auto-loads with live data

---

## Phase 6: Load Testing & Performance (1-2 days)

### 6.1 Load Test Script
- [ ] Create `scripts/load_test.py`:
  - Increase producer throughput to 500+ events/sec
  - Run for 120 seconds
  - Measure:
    - Events generated
    - Events processed
    - Consumer lag
    - Database insert latency
    - Anomaly detection latency

**Test parameters:**
```bash
python load_test.py --duration 120 --throughput 500
```

### 6.2 Monitoring During Load Test
- [ ] Watch Grafana dashboard
- [ ] Verify:
  - Revenue increasing
  - Consumer lag stable
  - Anomalies being detected
  - No errors in logs

### 6.3 Results Documentation
- [ ] Record results:
  - Sustained throughput (events/sec)
  - Consumer lag (seconds)
  - Latencies (p50, p95, p99)
  - Resource usage (CPU, memory)
- [ ] Screenshot Grafana during load test
- [ ] Include in README.md

**Expected outcome:** 500 events/sec sustained, consumer lag < 5 seconds

---

## Phase 7: Reliability & Resilience (1-2 days)

### 7.1 Consumer Crash Recovery
- [ ] Test consumer restart:
  - [ ] Crash consumer mid-stream
  - [ ] Verify no data loss (idempotent inserts)
  - [ ] Verify no duplication
  - [ ] Consumer resumes from correct offset

### 7.2 Health Checks
- [ ] Add to docker-compose.yml:
  - Redpanda: `rpk broker info`
  - PostgreSQL: `pg_isready`
  - Consumer: Check logs for errors
- [ ] Configure restart policies:
  - `on-failure` with retry count

### 7.3 Error Handling
- [ ] Producer:
  - [ ] Handle Kafka publish failures (retry logic)
  - [ ] Log anomaly injection
- [ ] Consumer:
  - [ ] Catch validation errors → dead_letter
  - [ ] Catch database errors → retry
  - [ ] Catch Kafka errors → restart
- [ ] Anomaly Detection:
  - [ ] Handle insufficient data (< 50 samples)
  - [ ] Handle model load failures
  - [ ] Graceful degradation on error

---

## Phase 8: Documentation (1-2 days)

### 8.1 README.md ✅ (Already created)
- [ ] Overview & goals
- [ ] Quick start (docker compose up)
- [ ] Architecture diagram
- [ ] System architecture (per layer)
- [ ] Data contract (Kafka topics, SLAs)
- [ ] dbt models & tests
- [ ] Load test results
- [ ] ADRs (3+ decisions)
- [ ] Grafana dashboard guide
- [ ] Known limitations
- [ ] What's next (future improvements)

### 8.2 ARCHITECTURE.md ✅ (Already created)
- [ ] Deep dive per layer
- [ ] Design decisions & trade-offs
- [ ] Code patterns (idempotent inserts, dead-letter, etc.)
- [ ] Performance characteristics
- [ ] Failure recovery scenarios

### 8.3 DATA_FLOW.md ✅ (Already created)
- [ ] Event lifecycle timeline
- [ ] Detailed flow per layer
- [ ] Data lineage diagram
- [ ] Failure scenarios & recovery
- [ ] Capacity planning

### 8.4 GETTING_STARTED.md ✅ (Already created)
- [ ] Prerequisites
- [ ] One-command startup
- [ ] Access services URLs
- [ ] Verify each layer
- [ ] Database exploration
- [ ] Common operations
- [ ] Troubleshooting

### 8.5 SUMMARY.md ✅ (Already created)
- [ ] Project summary card
- [ ] Elevator pitch
- [ ] Architecture at a glance
- [ ] Success criteria
- [ ] Key design decisions (ADRs)
- [ ] Interview gold moments
- [ ] Tech stack rationale

### 8.6 Code Comments
- [ ] Add docstrings to all Python modules
- [ ] Comment complex SQL (dbt models)
- [ ] Comment docker-compose services
- [ ] Add inline comments for non-obvious logic

---

## Phase 9: Polish & Final Testing (1 day)

### 9.1 Version Pinning
- [ ] Pin all Docker image versions
- [ ] Pin all Python package versions in requirements.txt
- [ ] Pin dbt, PostgreSQL versions
- [ ] Document minimum system requirements

### 9.2 Cross-Platform Testing
- [ ] Test on macOS
- [ ] Test on Linux (Ubuntu 20.04+)
- [ ] Verify all relative paths work
- [ ] Check for any hardcoded paths

### 9.3 Clean Startup Test
- [ ] Remove all containers: `docker compose down -v`
- [ ] Clean start: `docker compose up`
- [ ] Verify:
  - [ ] All services start within 30 seconds
  - [ ] Grafana dashboard loads
  - [ ] Data flows from Kafka to PostgreSQL
  - [ ] dbt models execute
  - [ ] Anomalies are detected

### 9.4 Git Cleanup
- [ ] Clean commit history (squash WIP commits)
- [ ] Remove debug code
- [ ] Remove `.env` file (keep `.env.example`)
- [ ] Add `.gitignore` entries for secrets, logs, etc.

### 9.5 Final Documentation Check
- [ ] README is complete and accurate
- [ ] All links work
- [ ] Code examples are copy-paste ready
- [ ] No typos or grammar errors
- [ ] Screenshots/diagrams are included

---

## Success Criteria Checklist

### P0 (Must-Have)
- [ ] Pipeline startup: < 30 seconds ✓
- [ ] Event throughput: 500 events/sec ✓
- [ ] Consumer restart recovery: At-least-once ✓

### P1 (Important)
- [ ] Data quality: dbt tests on all fct_ models ✓
- [ ] Anomaly detection latency: < 60 seconds ✓
- [ ] Dashboard provisioning: Auto on startup ✓
- [ ] README completeness: ADRs + load results ✓

### Final Checklist
- [ ] `docker compose up` works on clean machine
- [ ] All 6 layers operational
- [ ] Grafana dashboard shows live data
- [ ] Consumer survives restart without data loss
- [ ] Load test proves 500 events/sec
- [ ] README documents everything
- [ ] Code is commented and clean
- [ ] Git history is meaningful

---

## Stretch Goals (Extra Credit)

### Optional Enhancements
- [ ] Airflow DAG for weekly model retraining
- [ ] Railway/Render deployment (live URL)
- [ ] Data lineage visualization (dbt Docs)
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Kubernetes deployment (from Docker Compose)
- [ ] Advanced metrics (retention, LTV, CAC)
- [ ] Fraud rules engine (rules + ML ensemble)

---

## Estimated Timeline

| Phase | Duration | Notes |
|-------|----------|-------|
| 0: Setup | 4 hours | Git, Docker scaffolding |
| 1: Event Pipeline | 3-4 days | Kafka, producer, consumer |
| 2: Consumer & Validation | 2-3 days | Pydantic, idempotent inserts |
| 3: dbt Transformation | 3-4 days | Staging, marts, tests |
| 4: Anomaly Detection | 2-3 days | Isolation Forest, model registry |
| 5: Grafana Dashboard | 2 days | 4 panels, auto-provisioning |
| 6: Load Testing | 1-2 days | Performance validation |
| 7: Reliability | 1-2 days | Error handling, recovery |
| 8: Documentation | 1-2 days | README, ARCHITECTURE, etc. |
| 9: Polish | 1 day | Testing, cleanup |
| **Total** | **2-3 weeks** | 20-30 hours/week |

---

## Build Order (Recommended)

1. **Week 1, Day 1-2:** Phase 0-1 (Docker, Kafka, producer)
2. **Week 1, Day 3-4:** Phase 2 (Consumer, validation)
3. **Week 1, Day 5:** Phase 3 (dbt foundation)
4. **Week 2, Day 1-2:** Phase 3 (dbt models & tests)
5. **Week 2, Day 3:** Phase 4 (Anomaly detection)
6. **Week 2, Day 4:** Phase 5 (Grafana dashboard)
7. **Week 2, Day 5:** Phase 6 (Load testing)
8. **Week 3, Day 1:** Phase 7 (Reliability)
9. **Week 3, Day 2-3:** Phase 8-9 (Documentation & polish)

---

## When You're Done

1. **Verify:** `docker compose up` works on fresh machine
2. **Test:** Run load test, capture results
3. **Document:** README includes ADRs + load results
4. **Submit:** Push to GitHub with clear description
5. **Prepare:** Be ready to explain each ADR & design decision

Good luck! 🚀

