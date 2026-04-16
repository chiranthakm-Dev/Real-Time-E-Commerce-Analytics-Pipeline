# Real-Time E-Commerce Analytics Pipeline — To-Do List

## Overview
This to-do list breaks down the entire project into actionable tasks across 9 implementation phases. Estimated timeline: **2-3 weeks** (20-30 hours/week).

**Progress:** [██████████████████████░░] 55% Complete (Phase 2: Consumer ✅)

---

## Phase 0: Project Setup (2-4 hours)

### 0.1 Repository & Environment
- [x] Clone repository locally
- [x] Create `.gitignore` (Python, Docker, IDE, secrets)
  - [x] Ignore `*.pyc`, `__pycache__/`, `.env`
  - [x] Ignore `.vscode/`, `.idea/`
  - [x] Ignore Docker volumes & logs
- [x] Create `.env.example` (template, no secrets)
  - [x] Include: `POSTGRES_PASSWORD`, `PRODUCER_THROUGHPUT`, `GRAFANA_PASSWORD`
- [x] Create `requirements.txt` (Python dependencies)
  - [x] Producer: faker, confluent-kafka
  - [x] Consumer: pydantic, psycopg2, confluent-kafka
  - [x] Anomaly: scikit-learn, prometheus_client, pandas
- [x] Initialize directory structure:
  - [x] `src/producer/`, `src/consumer/`, `src/anomaly_detector/`, `src/shared/`
  - [x] `dbt/`, `postgres/`, `docker/`, `grafana/`
  - [x] `logs/`, `data/`

**Estimated time:** 30 min | **Status:** ✅ Completed (1 hour)

---

## Phase 1: Event Pipeline (3-4 days)

### 1.1 Redpanda & Kafka Setup
- [x] Create `docker-compose.yml` with Redpanda service
  - [x] Image: `docker.redpanda.com/redpanda:v23.3.3`
  - [x] Ports: 9092 (Kafka API), 9644 (Admin), 8082 (PandaProxy), 8081 (Schema Registry)
  - [x] Health check: `rpk cluster info`
  - [x] Dev mode with 1 CPU, 1GB memory
- [x] Create Kafka topics via scripts:
  - [x] `page_views` (2 partitions, 1h retention, snappy compression)
  - [x] `cart_events` (2 partitions, 1h retention, snappy compression)
  - [x] `purchases` (2 partitions, 1h retention, snappy compression)
- [x] Add setup scripts: `setup_kafka_topics.sh` and `kafka_topics.py`
- [x] Test: Scripts verify topic creation and provide consume commands

**Estimated time:** 4 hours | **Status:** ✅ Completed (2 hours)

### 1.2 Event Producer
- [x] Create `src/shared/schemas.py` (Pydantic models)
  - [x] Define `PageViewEvent` (event_id, user_id, product_id, ts, url, referrer)
  - [x] Define `CartEvent` (event_id, user_id, product_id, action, quantity, price)
  - [x] Define `PurchaseEvent` (event_id, user_id, order_id, items, total_amount)
  - [x] Add `EventEnvelope` for Kafka messaging
- [x] Create `src/producer/anomaly_injector.py`
  - [x] Fraud: revenue *= 5-20x for purchases
  - [x] Bot traffic: mark events for burst generation
  - [x] Data quality: missing fields, invalid values
  - [x] Configurable injection rate (0.5% default)
- [x] Create `src/producer/producer.py`
  - [x] Generate page_views: ~200 events/sec (40%)
  - [x] Generate cart_events: ~150 events/sec (30%)
  - [x] Generate purchases: ~150 events/sec (30%)
  - [x] Total: 500 events/sec configurable throughput
  - [x] Use partition key: `user_id` for session ordering
  - [x] Kafka publishing with delivery callbacks and error handling
  - [x] Structured logging every 10 seconds with stats

**Expected outcome:** Producer publishes to Kafka; messages visible in `rpk topic consume`

**Estimated time:** 8 hours | **Status:** ✅ Completed (6 hours)

### 1.3 PostgreSQL Setup
- [x] Create `postgres/init.sql`
  - [x] Database: `analytics` (configured via POSTGRES_DB)
  - [x] Schemas: `raw`, `staging`, `marts`, `metrics`
  - [x] Table: `raw.events` (append-only event storage)
    ```sql
    CREATE TABLE raw.events (
        event_id UUID PRIMARY KEY,
        event_type VARCHAR(50) NOT NULL,
        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
        user_id VARCHAR(100), session_id VARCHAR(100),
        product_id VARCHAR(100), category VARCHAR(100),
        price DECIMAL(10,2), quantity INTEGER,
        order_id VARCHAR(100), total_amount DECIMAL(10,2),
        currency VARCHAR(3) DEFAULT 'USD',
        metadata JSONB, created_at TIMESTAMP DEFAULT NOW()
    );
    ```
  - [x] Table: `raw.anomalies` (anomaly detection results)
  - [x] Table: `staging.processed_events` (idempotent processing)
  - [x] Tables: `metrics.*` (consumer/producer/anomaly metrics)
  - [x] Indexes: event_id, user_id, timestamp, event_type
- [x] Add to `docker-compose.yml` with health checks
- [x] Configure via environment variables

**Estimated time:** 6 hours | **Status:** ✅ Completed (4 hours)
        category VARCHAR(100),
        revenue DECIMAL(10, 2),
        currency VARCHAR(3),
        ts TIMESTAMP,
        country VARCHAR(2),
        created_at TIMESTAMP DEFAULT NOW()
    );
    ```
  - [ ] Table: `dead_letter` (validation failures)
    ```sql
    CREATE TABLE dead_letter (
        id BIGSERIAL PRIMARY KEY,
        event_id UUID,
        raw_payload JSONB,
        error_reason TEXT,
        error_type VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW()
    );
    ```
  - [ ] Indexes: `event_id`, `user_id`, `created_at`
- [x] Add PostgreSQL to `docker-compose.yml`
  - [x] Image: `postgres:15-alpine`
  - [x] Port: 5432 with health checks
  - [x] Volume: postgres-data persistence
  - [x] Environment variables for config
- [x] Test: Schema created on container startup

**Estimated time:** 6 hours | **Status:** ✅ Completed (4 hours)

---

## Phase 2: Consumer & Validation (2-3 days)

### 2.1 Consumer Foundation
- [x] Create `src/consumer/consumer.py` (main consumer service)
  - [x] Pydantic validation with business rules:
    - [x] `timestamp` not in future (1 min skew allowed)
    - [x] `total_amount` >= 0, `price` >= 0
    - [x] `quantity` > 0 for cart/purchase events
    - [x] Event structure validation via schemas
- [x] Create `src/consumer/database.py` (integrated in consumer.py)
  - [x] PostgreSQL connection with transactions
  - [x] Idempotent insert with `ON CONFLICT DO NOTHING`:
    ```sql
    INSERT INTO raw.events (...) VALUES (...)
    ON CONFLICT (event_id) DO NOTHING;
    ```
  - [x] Dead-letter queue for validation failures
  - [x] Processed events tracking for idempotency
- [x] Consumer implementation:
  - [x] Kafka consumer config with manual offset commits
  - [x] Batch processing (configurable batch size)
  - [x] Exactly-once processing with transaction boundaries
  - [x] Error handling: ValidationError → dead letter, DB errors → rollback
  - [x] Comprehensive logging every 1000 events with throughput metrics
  - [x] Consumer group support for horizontal scaling

**Expected outcome:** Data flows from Kafka to PostgreSQL with validation

**Estimated time:** 8 hours | **Status:** ✅ Completed (6 hours)

### 2.2 Idempotent Insert Pattern (Testing)
- [ ] Test consumer restart safety:
  - [ ] Generate 1000 events
  - [ ] Stop consumer after 500 processed (before offset commit)
  - [ ] Restart consumer
  - [ ] Verify no duplication in `raw_events`
  - [ ] Verify offset resumes correctly
- [ ] Test dead-letter queue:
  - [ ] Generate invalid event (revenue = 50,000)
  - [ ] Verify written to `dead_letter` table
  - [ ] Verify error_reason logged
  - [ ] Verify consumer continues (not stuck)

**Estimated time:** 4 hours | **Status:** Not Started

### 2.3 Integration
- [ ] Add consumer service to `docker-compose.yml`
  - [ ] Build from `src/consumer/Dockerfile`
  - [ ] Depends on: `redpanda`, `postgres`
  - [ ] Restart policy: `on-failure`
- [ ] Test full integration:
  - [ ] `docker compose up`
  - [ ] Check logs: producer sending, consumer receiving
  - [ ] Query PostgreSQL: `SELECT COUNT(*) FROM raw_events;` (growing)

**Estimated time:** 2 hours | **Status:** Not Started

---

## Phase 3: Data Transformation with dbt (3-4 days)

### 3.1 dbt Project Setup
- [ ] Initialize dbt project: `dbt init`
- [ ] Create `dbt/profiles.yml` (PostgreSQL connection)
  - [ ] Host: `postgres`
  - [ ] Port: `5432`
  - [ ] Database: `analytics`
- [ ] Create `dbt/dbt_project.yml`
  - [ ] Project name: `ecommerce_analytics`
  - [ ] Version: `1.0`
  - [ ] On-run-end hook: trigger Slack alert on test failure
- [ ] Create directory structure:
  - [ ] `dbt/models/staging/`, `dbt/models/marts/`, `dbt/models/metrics/`
  - [ ] `dbt/tests/custom/`
  - [ ] `dbt/macros/`

**Estimated time:** 2 hours | **Status:** Not Started

### 3.2 Staging Models (Type Casting & Filtering)
- [ ] Create `dbt/models/staging/stg_page_views.sql`
  - [ ] Source: `raw_events`
  - [ ] Cast columns: `event_id::UUID`, `ts::TIMESTAMP`
  - [ ] Filter: user_id NOT LIKE 'test_%'
  - [ ] Filter: ts > NOW() - INTERVAL '7 days'
- [ ] Create `dbt/models/staging/stg_cart_events.sql` (similar)
- [ ] Create `dbt/models/staging/stg_purchases.sql` (similar)
  - [ ] Add validation: revenue > 0 AND currency IN ('EUR', 'USD')
- [ ] Test: `dbt compile` (all models compile without errors)

**Estimated time:** 4 hours | **Status:** Not Started

### 3.3 Mart Models (Business Logic)
- [ ] Create `dbt/models/marts/fct_purchases.sql`
  - [ ] Source: `stg_purchases`
  - [ ] Columns: event_id, user_id, session_id, product_id, category, revenue, ts
  - [ ] Add computed:
    - [ ] `purchase_year`, `purchase_month`, `purchase_day_of_week`, `purchase_hour`
    - [ ] `data_quality_flag` (anomaly detection: revenue > 10,000?)
  - [ ] Materialized as: `table` (not view)
- [ ] Create `dbt/models/marts/dim_users.sql`
  - [ ] Grain: one row per user
  - [ ] Columns: user_id, first_purchase_date, total_purchases, lifetime_value
  - [ ] Source: `fct_purchases`
- [ ] Create `dbt/models/marts/fct_conversion_funnel.sql`
  - [ ] Grain: one row per session
  - [ ] Columns: session_id, had_page_view (bool), had_cart (bool), had_purchase (bool)

**Expected outcome:** Models materialize with data visible in Grafana

**Estimated time:** 6 hours | **Status:** Not Started

### 3.4 Metrics Layer
- [ ] Create `dbt/models/metrics/daily_revenue.sql`
  - [ ] Grain: date + category + country
  - [ ] Columns: revenue_date, category, country, count, sum_revenue, avg_revenue, stddev
  - [ ] Filter: last 30 days

**Estimated time:** 2 hours | **Status:** Not Started

### 3.5 Comprehensive Tests
- [ ] Create `dbt/models/schema.yml`
  - [ ] Generic tests:
    - [ ] `fct_purchases.event_id`: unique, not_null
    - [ ] `fct_purchases.revenue`: not_null, expression_is_true (revenue > 0)
    - [ ] `fct_purchases.country`: accepted_values
  - [ ] Properties: descriptions, types
- [ ] Create custom macros in `dbt/macros/`:
  - [ ] `test_no_future_dates.sql` (ts not in future)
  - [ ] `test_revenue_sane.sql` (revenue < 1,000,000)
- [ ] Test: `dbt test` (all tests pass)

**Estimated time:** 3 hours | **Status:** Not Started

### 3.6 Scheduling & Alerting
- [ ] Create Dockerfile for dbt: `dbt/Dockerfile`
- [ ] Add dbt service to `docker-compose.yml`:
  - [ ] Run: `dbt run && dbt test`
  - [ ] Schedule: hourly via cron (or manual trigger)
  - [ ] On-run-end hook: send Slack webhook if tests fail
- [ ] Create `.env` variable: `SLACK_WEBHOOK_URL` (placeholder)
- [ ] Test: `dbt run` produces data; `dbt test` validates

**Estimated time:** 3 hours | **Status:** Not Started

---

## Phase 4: Anomaly Detection (2-3 days)

### 4.1 Isolation Forest Model
- [ ] Create `src/anomaly_detection/detector.py`
  - [ ] Class: `AnomalyDetector`
  - [ ] Constructor:
    - [ ] Initialize `IsolationForest(contamination=0.01, n_estimators=100)`
    - [ ] Define features: `revenue`, `hour_of_day`, `events_in_session`, `time_since_last_purchase`
  - [ ] Method: `compute_features(purchases_df)` → returns feature matrix
  - [ ] Method: `predict(purchases_df)` → returns predictions + scores
- [ ] Feature engineering:
  - [ ] Revenue: normalized by z-score
  - [ ] Hour of day: EXTRACT(HOUR FROM ts)
  - [ ] Events in session: COUNT per session_id
  - [ ] Time since last: (current_ts - prev_ts).seconds
- [ ] Model training:
  - [ ] Use last 500 purchases as training window
  - [ ] Train on feature matrix
  - [ ] Save model to PostgreSQL (pickle)

**Estimated time:** 6 hours | **Status:** Not Started

### 4.2 Polling Architecture
- [ ] Create `src/anomaly_detection/main.py`
  - [ ] Main loop:
    - [ ] Every 60 seconds:
      - [ ] Fetch last 500 purchases from `fct_purchases`
      - [ ] Compute features
      - [ ] Predict with model
      - [ ] Insert flagged anomalies to `anomalies` table
      - [ ] Increment Prometheus counter
  - [ ] Error handling:
    - [ ] If < 50 samples, log and skip
    - [ ] If model load fails, retry
    - [ ] If database error, retry
  - [ ] Logging: every 10 detections, log progress

**Expected outcome:** Anomalies table grows; every 60s, new entries appear

**Estimated time:** 4 hours | **Status:** Not Started

### 4.3 Anomaly Storage & Model Registry
- [ ] Create `anomalies` table in PostgreSQL (via migration):
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
- [ ] Create `model_registry` table:
  ```sql
  CREATE TABLE model_registry (
      model_version INT PRIMARY KEY,
      training_date TIMESTAMP,
      feature_set TEXT,
      contamination FLOAT,
      model_bytes BYTEA,
      status VARCHAR(20)  -- 'active', 'deprecated'
  );
  ```
- [ ] Create `src/anomaly_detection/model_registry.py`
  - [ ] Function: `save_model(model, version, metadata)`
  - [ ] Function: `load_latest_model()`
  - [ ] Function: `list_all_models()`

**Estimated time:** 3 hours | **Status:** Not Started

### 4.4 Prometheus Metrics
- [ ] Create `src/anomaly_detection/metrics.py`
  - [ ] Initialize `CollectorRegistry()`
  - [ ] Counter: `anomaly_count_total`
  - [ ] Gauge: `latest_anomaly_score`
  - [ ] HTTP endpoint: `/metrics` (port 8000)
- [ ] Start metrics server on container startup
- [ ] Test: `curl http://localhost:8000/metrics`

**Estimated time:** 2 hours | **Status:** Not Started

### 4.5 Integration
- [ ] Create `Dockerfile` for anomaly detection
- [ ] Add to `docker-compose.yml`:
  - [ ] Build from `src/anomaly_detection/Dockerfile`
  - [ ] Port: 8000 (Prometheus endpoint)
  - [ ] Depends on: `postgres`
- [ ] Test: `docker compose up` → anomalies detected every 60s

**Estimated time:** 2 hours | **Status:** Not Started

---

## Phase 5: Grafana Dashboard (2 days)

### 5.1 Datasource & Provisioning
- [ ] Create `grafana/provisioning/datasources/postgres.yml`
  - [ ] Connection: `postgres:5432/analytics`
  - [ ] User: `postgres`
  - [ ] Password from env: `${POSTGRES_PASSWORD}`
- [ ] Create `grafana/provisioning/dashboards/dashboard.yml`
  - [ ] Reference: `ecommerce_dashboard.json`
  - [ ] Folder: `E-Commerce`

**Estimated time:** 1 hour | **Status:** Not Started

### 5.2 Dashboard JSON Creation
- [ ] Create `grafana/provisioning/dashboards/ecommerce_dashboard.json`
  - [ ] Dashboard title: "Real-Time E-Commerce Analytics"
  - [ ] Refresh interval: 5 seconds
  - [ ] 4 panels (see below)

**Panel 1: Conversion Funnel (Bar Chart)**
- [ ] Query: % of sessions with page_view, cart, purchase
- [ ] X-axis: ["Page Views", "Cart Adds", "Purchases"]
- [ ] Y-axis: Percentage
- [ ] Colors: Green → Red gradient

**Panel 2: Revenue Over Time (Line Chart)**
- [ ] Query: Hourly revenue by category (last 24h)
- [ ] X-axis: Time (hourly)
- [ ] Y-axis: Revenue (EUR)
- [ ] Lines: One per category (electronics, clothing, etc.)
- [ ] Overlays: Anomalies as red dots/annotations

**Panel 3: Cohort Retention Heatmap**
- [ ] Query: Users by first-purchase week, % returning in weeks 1-4
- [ ] Rows: First purchase weeks
- [ ] Columns: Weeks 1-4
- [ ] Values: % retention (0-100)
- [ ] Color scale: White (0%) → Green (100%)

**Panel 4: Data Quality (Table)**
- [ ] Query: dbt test results from last run
- [ ] Columns: Test name, Status, Last run time
- [ ] Conditional formatting: Green (PASS), Red (FAIL)

**Estimated time:** 4 hours | **Status:** Not Started

### 5.3 Auto-Provisioning
- [ ] Create `grafana/Dockerfile`
  - [ ] Base: `grafana/grafana:latest`
  - [ ] Copy: provisioning YAMLs
- [ ] Add to `docker-compose.yml`:
  - [ ] Image: built from `grafana/Dockerfile`
  - [ ] Port: 3000
  - [ ] Volumes: provisioning directory
  - [ ] Env: `GF_SECURITY_ADMIN_PASSWORD`, datasource config
- [ ] Test:
  - [ ] `docker compose up`
  - [ ] Visit http://localhost:3000
  - [ ] Dashboard auto-loads
  - [ ] No manual configuration needed

**Estimated time:** 2 hours | **Status:** Not Started

---

## Phase 6: Load Testing & Performance (1-2 days)

### 6.1 Load Test Script
- [ ] Create `scripts/load_test.py`
  - [ ] Arguments: `--duration 120`, `--throughput 500`
  - [ ] Measure:
    - [ ] Events generated (total)
    - [ ] Events processed (consumer lag)
    - [ ] Latencies: p50, p95, p99
    - [ ] Resource usage: CPU, memory
  - [ ] Output: JSON + human-readable report
  - [ ] Duration: 120 seconds sustained load

**Expected outcome:** 500 events/sec sustained, consumer lag < 5 seconds

**Estimated time:** 3 hours | **Status:** Not Started

### 6.2 Monitoring During Load Test
- [ ] Instructions for watching Grafana:
  - [ ] Revenue should increase monotonically
  - [ ] Anomaly count should grow (1% of 500/sec)
  - [ ] Consumer lag should stay < 5 seconds
  - [ ] No errors in logs
- [ ] Screenshot results:
  - [ ] Grafana dashboard during peak load
  - [ ] Console output (throughput, latency)

**Estimated time:** 2 hours | **Status:** Not Started

### 6.3 Results Documentation
- [ ] Record metrics in `README.md`:
  - [ ] Sustained throughput: X events/sec
  - [ ] Consumer lag: X seconds
  - [ ] P95 latency: X seconds
  - [ ] Resource usage: CPU X%, Memory X GB
- [ ] Include screenshots (PNG/JPEG)
- [ ] Document test setup (duration, load parameters)

**Estimated time:** 1 hour | **Status:** Not Started

---

## Phase 7: Reliability & Resilience (1-2 days)

### 7.1 Consumer Crash Recovery
- [ ] Test scenario:
  - [ ] Run pipeline 30 seconds
  - [ ] Kill consumer: `docker kill consumer-1`
  - [ ] Restart: `docker compose up -d consumer`
  - [ ] Verify:
    - [ ] No data loss (count in `raw_events` same as events generated)
    - [ ] No duplication (unique event_ids)
    - [ ] Consumer resumes from correct offset
- [ ] Document in README (recovery scenario)

**Estimated time:** 2 hours | **Status:** Not Started

### 7.2 Health Checks
- [ ] Add health checks to `docker-compose.yml`:
  - [ ] Redpanda: `rpk broker info`
  - [ ] PostgreSQL: `pg_isready -U postgres`
  - [ ] Consumer: Check logs every 30 seconds
- [ ] Add restart policies:
  - [ ] Producer: `on-failure, max-retries=3`
  - [ ] Consumer: `on-failure, max-retries=5`
  - [ ] Anomaly detection: `on-failure, max-retries=3`

**Estimated time:** 1 hour | **Status:** Not Started

### 7.3 Error Handling in Code
- [ ] Producer:
  - [ ] Kafka publish failures: retry up to 3 times with exponential backoff
  - [ ] Log every error to stderr
- [ ] Consumer:
  - [ ] ValidationError → log to dead_letter, continue
  - [ ] DatabaseError → retry 3 times, then crash (restart policy will recover)
  - [ ] KafkaError → log, don't commit offset, crash
- [ ] Anomaly Detection:
  - [ ] Model load failure → retry every 10 seconds
  - [ ] Database connection error → retry, log
  - [ ] Insufficient data → skip this cycle, continue

**Estimated time:** 3 hours | **Status:** Not Started

---

## Phase 8: Documentation (1-2 days)

### 8.1 README.md ✅ (Already created)
- [x] Overview & goals
- [x] Quick start
- [x] Architecture diagram
- [x] System components (6 layers)
- [x] Data contract
- [x] dbt models
- [x] Load test results
- [x] ADRs
- [x] Known limitations
- [x] What's next

**Status:** ✅ Complete

### 8.2 ARCHITECTURE.md ✅ (Already created)
- [x] Deep dive per layer
- [x] Design patterns
- [x] Code examples
- [x] Performance characteristics

**Status:** ✅ Complete

### 8.3 DATA_FLOW.md ✅ (Already created)
- [x] Event lifecycle
- [x] Failure scenarios
- [x] Capacity planning

**Status:** ✅ Complete

### 8.4 GETTING_STARTED.md ✅ (Already created)
- [x] Setup guide
- [x] Troubleshooting
- [x] Common operations

**Status:** ✅ Complete

### 8.5 SUMMARY.md ✅ (Already created)
- [x] Executive summary
- [x] Interview talking points

**Status:** ✅ Complete

### 8.6 Code Comments
- [ ] Add docstrings to all Python files:
  - [ ] `src/producer/main.py`: 20+ docstrings
  - [ ] `src/consumer/main.py`: 20+ docstrings
  - [ ] `src/anomaly_detection/detector.py`: 15+ docstrings
- [ ] Add comments to complex SQL:
  - [ ] `dbt/models/marts/fct_purchases.sql`: explain joins & computations
  - [ ] `dbt/models/marts/fct_conversion_funnel.sql`: explain logic
- [ ] Add comments to `docker-compose.yml`: explain each service

**Estimated time:** 3 hours | **Status:** Not Started

---

## Phase 9: Polish & Final Testing (1 day)

### 9.1 Version Pinning
- [ ] Pin all Docker image versions in `docker-compose.yml`:
  - [ ] `postgres:15-alpine` (not latest)
  - [ ] `docker.redpanda.com/redpanda:v23.1.14` (specific version)
  - [ ] `grafana/grafana:10.0.0` (specific version)
- [ ] Pin Python package versions in `requirements.txt`:
  - [ ] `faker==18.13.0`
  - [ ] `confluent-kafka==2.2.0`
  - [ ] `pydantic==2.0.0`
  - [ ] `scikit-learn==1.3.0`
- [ ] Document minimum system requirements:
  - [ ] Docker v20.10+
  - [ ] RAM: 4 GB minimum, 8 GB recommended
  - [ ] Disk: 5 GB free

**Estimated time:** 1 hour | **Status:** Not Started

### 9.2 Cross-Platform Testing
- [ ] Test on macOS:
  - [ ] `docker compose up`
  - [ ] Verify all services start
  - [ ] Check Grafana dashboard
- [ ] Test on Linux (Ubuntu):
  - [ ] Same verification
- [ ] Check for hardcoded paths:
  - [ ] Search for `/Users/apple/` → replace with relative paths
  - [ ] Search for absolute Windows paths → replace

**Estimated time:** 1 hour | **Status:** Not Started

### 9.3 Clean Startup Test (Final Validation)
- [ ] Remove all containers: `docker compose down -v`
- [ ] Delete all local data:
  - [ ] Remove PostgreSQL volumes
  - [ ] Remove Redpanda state
- [ ] Fresh start: `docker compose up`
- [ ] Verify checklist:
  - [ ] All services start within 30 seconds ✅
  - [ ] Producer generating events (logs show "Generated 100 events")
  - [ ] Consumer processing events (PostgreSQL has rows)
  - [ ] dbt models run successfully
  - [ ] Grafana dashboard loads at http://localhost:3000
  - [ ] Anomalies detected and visible in dashboard
  - [ ] No errors in any service logs

**Estimated time:** 1 hour | **Status:** Not Started

### 9.4 Git Cleanup
- [ ] Clean commit history:
  - [ ] Squash WIP commits
  - [ ] Meaningful commit messages
  - [ ] No debug code in final commits
- [ ] Remove secrets:
  - [ ] No `.env` file in repo
  - [ ] `.env.example` provided as template
  - [ ] No credentials in code
- [ ] `.gitignore` complete:
  - [ ] `*.pyc`, `__pycache__/`
  - [ ] `.env`, `.env.local`
  - [ ] `.vscode/`, `.idea/`, IDE files
  - [ ] Docker volumes, logs
  - [ ] `dbt/target/`, `dbt/logs/`

**Estimated time:** 30 min | **Status:** Not Started

### 9.5 Final Documentation Review
- [ ] README.md:
  - [ ] No broken links
  - [ ] All code examples copy-paste ready
  - [ ] Screenshots/diagrams present
  - [ ] Spelling & grammar correct
- [ ] Code comments:
  - [ ] All public functions documented
  - [ ] Complex logic explained
  - [ ] No TODO comments left
- [ ] IMPLEMENTATION_ROADMAP.md:
  - [ ] Timestamps realistic
  - [ ] Checkboxes accurate
  - [ ] Success criteria clear

**Estimated time:** 1 hour | **Status:** Not Started

---

## Post-Launch: Optional Enhancements (Stretch Goals)

### Airflow DAG for Weekly Model Retraining
- [ ] Create `dags/weekly_anomaly_retraining.py`
  - [ ] Schedule: Monday 2 AM
  - [ ] Tasks: fetch_data → train_model → evaluate → register
  - [ ] Triggers: alert on new model deployment
- [ ] Add Airflow to `docker-compose.yml`

**Estimated time:** 4-6 hours | **Priority:** Nice-to-have

### Cloud Deployment (Railway/Render)
- [ ] Deploy PostgreSQL (managed service)
- [ ] Deploy Redpanda (managed or containerized)
- [ ] Deploy Python services (containers)
- [ ] Configure live URL in README
- [ ] Test end-to-end on live platform

**Estimated time:** 3-4 hours | **Priority:** Nice-to-have

### Advanced Metrics & Retention Analysis
- [ ] Create cohort retention dashboard
- [ ] Implement customer lifetime value (LTV) tracking
- [ ] Add conversion rate trending
- [ ] Implement RFM (Recency, Frequency, Monetary) scoring

**Estimated time:** 4-6 hours | **Priority:** Nice-to-have

---

## Success Criteria Checklist (Final Verification)

### P0 (Must-Have)
- [ ] Pipeline startup time: < 30 seconds
- [ ] Event throughput: 500 events/sec sustained
- [ ] Consumer restart recovery: No data loss or duplication

### P1 (Important)
- [ ] Data quality tests: All dbt tests pass
- [ ] Anomaly detection latency: < 60 seconds
- [ ] Dashboard provisioning: Auto-loads on startup
- [ ] README completeness: ADRs + load results included

### Final Checks
- [ ] `docker compose up` works on fresh machine ✅
- [ ] All 6 layers operational within 30 seconds ✅
- [ ] Grafana dashboard shows live data ✅
- [ ] Consumer survives restart without data loss ✅
- [ ] Load test proves 500 events/sec ✅
- [ ] README documents everything ✅
- [ ] Code is commented and clean ✅
- [ ] Git history is meaningful ✅

---

## Timeline Summary

| Phase | Duration | Cumulative |
|-------|----------|-----------|
| 0: Setup | 4 hours | 4 hours |
| 1: Event Pipeline | 15 hours | 19 hours |
| 2: Consumer | 14 hours | 33 hours |
| 3: dbt | 18 hours | 51 hours |
| 4: Anomaly Detection | 17 hours | 68 hours |
| 5: Grafana | 8 hours | 76 hours |
| 6: Load Testing | 6 hours | 82 hours |
| 7: Reliability | 6 hours | 88 hours |
| 8: Documentation | 3 hours | 91 hours |
| 9: Polish | 5 hours | 96 hours |
| **Total** | **~2-3 weeks** | **96+ hours** |

---

## Getting Started

1. Start with **Phase 0** (Project Setup)
2. Follow phases sequentially (1-9)
3. Update checkboxes as you complete tasks
4. Reference documentation files for patterns & examples
5. Test at each phase milestone
6. Document any deviations from the plan

**Good luck! 🚀**

