# stream-lens

> A real-time e-commerce analytics pipeline — Kafka ingestion, dbt transformations, ML anomaly detection, and a live Grafana dashboard. Built with production data engineering practices.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Apache Kafka](https://img.shields.io/badge/Kafka-3.7-231F20?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org)
[![dbt](https://img.shields.io/badge/dbt-1.8-FF694B?style=flat-square&logo=dbt&logoColor=white)](https://getdbt.com)
[![Grafana](https://img.shields.io/badge/Grafana-10.4-F46800?style=flat-square&logo=grafana&logoColor=white)](https://grafana.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/dbt%20tests-passing-brightgreen?style=flat-square)]()

---

## What this is

E-commerce teams fly blind without real-time visibility into their funnel. Batch ETL jobs that run at midnight don't catch a broken checkout flow at 2pm on a Friday.

This project is an end-to-end streaming analytics pipeline that ingests clickstream events (page views, add-to-cart, purchases, refunds) via Kafka, transforms them through layered dbt models, runs a lightweight anomaly detection model to flag unusual revenue patterns, and serves everything through a live Grafana dashboard — with a Slack alert when something looks wrong.

Every step is idempotent. Running the pipeline twice produces the same result. That's not a nice-to-have — it's the foundation of trustworthy data.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────────────────┐
│  Event producer  │────▶│                    Kafka (3 topics)                  │
│  (Faker-based)  │     │  clickstream.raw · orders.raw · refunds.raw          │
└─────────────────┘     └──────────────┬───────────────────────────────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │     Python consumer          │
                         │  Validates · deserialises    │
                         │  Writes to raw Postgres      │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │          dbt models          │
                         │  staging → marts → metrics   │
                         │  + data quality tests        │
                         └──────┬───────────┬──────────┘
                                │           │
               ┌────────────────▼─┐   ┌─────▼────────────────┐
               │  Anomaly detector │   │   Grafana dashboard   │
               │  Isolation Forest │   │   Live · auto-refresh │
               │  + Slack alert    │   └──────────────────────┘
               └──────────────────┘
```

### Pipeline layers

**Layer 1 — Raw (Kafka → Postgres):** Events land in append-only raw tables with no transformation. The consumer is a Kafka consumer group — multiple instances can run in parallel, each handling different topic partitions.

**Layer 2 — Staging (dbt):** Light cleaning only — cast types, rename columns to snake_case, add `ingested_at` timestamps. No business logic here. One staging model per raw topic.

**Layer 3 — Marts (dbt):** Business-level aggregations — conversion funnel by session, revenue by product category, refund rate by day. These are the tables Grafana reads.

**Layer 4 — Anomaly detection:** A nightly (or triggered) Isolation Forest scan over the `mart_revenue_hourly` table. Flags hours where revenue deviates unexpectedly and writes results to `anomaly_flags`. Slack webhook fires on any new flag.

---

## Quickstart

**Prerequisites:** Docker + Docker Compose, Python 3.11+

```bash
git clone https://github.com/yourusername/stream-lens.git
cd stream-lens

# Start Kafka, Zookeeper, Postgres, Grafana
docker compose up -d

# Install Python dependencies
pip install -r requirements.txt

# Run dbt to create all tables and views
dbt deps && dbt run && dbt test

# Start the event producer (generates ~100 events/sec)
python producer/generate_events.py

# Start the Kafka consumer (in a separate terminal)
python consumer/ingest.py

# Open Grafana at http://localhost:3000  (admin / admin)
```

Grafana dashboard auto-imports from `grafana/dashboards/ecommerce.json`. You'll see live data within 30 seconds of starting the producer.

---

## Data model

### Raw tables (append-only, never modified)

```sql
-- Written by Kafka consumer, never modified by dbt
raw_clickstream_events (
    event_id        UUID,
    session_id      UUID,
    user_id         UUID,
    event_type      TEXT,    -- 'page_view' | 'add_to_cart' | 'checkout_start' | 'purchase'
    page_url        TEXT,
    product_id      UUID,
    metadata        JSONB,
    kafka_offset    BIGINT,  -- idempotency key — duplicate events are rejected
    received_at     TIMESTAMPTZ
)

raw_orders (
    order_id        UUID,
    user_id         UUID,
    total_amount    NUMERIC(10,2),
    currency        TEXT,
    status          TEXT,
    kafka_offset    BIGINT,
    received_at     TIMESTAMPTZ
)
```

### Key mart tables (built by dbt)

```sql
-- Conversion funnel — updated every 5 minutes via dbt Cloud or Airflow
mart_conversion_funnel (
    window_start        TIMESTAMPTZ,
    window_end          TIMESTAMPTZ,
    page_views          BIGINT,
    add_to_cart         BIGINT,
    checkout_starts     BIGINT,
    purchases           BIGINT,
    conversion_rate     NUMERIC(5,4)   -- purchases / page_views
)

-- Revenue anomaly flags
anomaly_flags (
    id              UUID,
    window_start    TIMESTAMPTZ,
    actual_revenue  NUMERIC(10,2),
    expected_range  NUMRANGE,
    anomaly_score   NUMERIC(6,4),      -- Isolation Forest: higher = more anomalous
    alerted         BOOLEAN,
    created_at      TIMESTAMPTZ
)
```

---

## dbt project structure

```
dbt/
├── models/
│   ├── staging/
│   │   ├── stg_clickstream.sql        # type casts, rename, dedup
│   │   ├── stg_orders.sql
│   │   └── stg_refunds.sql
│   ├── marts/
│   │   ├── mart_conversion_funnel.sql
│   │   ├── mart_revenue_hourly.sql
│   │   ├── mart_revenue_by_category.sql
│   │   └── mart_refund_rate_daily.sql
│   └── metrics/
│       └── revenue_anomaly_input.sql  # pre-aggregated for the ML model
├── tests/
│   ├── generic/
│   │   └── assert_revenue_non_negative.sql   # custom dbt test
│   └── schema.yml                     # column-level tests: not_null, unique, accepted_values
├── macros/
│   └── get_window_boundaries.sql
└── dbt_project.yml
```

### Data quality tests (schema.yml excerpt)

```yaml
models:
  - name: stg_orders
    columns:
      - name: order_id
        tests: [unique, not_null]
      - name: total_amount
        tests:
          - not_null
          - dbt_utils.expression_is_true:
              expression: ">= 0"
              name: revenue_non_negative
      - name: currency
        tests:
          - accepted_values:
              values: ['EUR', 'USD', 'GBP']
      - name: status
        tests:
          - accepted_values:
              values: ['pending', 'completed', 'refunded', 'cancelled']
```

If any test fails, the Airflow DAG stops and a Slack alert fires. No silent bad data reaching the dashboard.

---

## Anomaly detection

The `anomaly_detector/detect.py` script runs on a schedule (via Airflow or cron):

```python
from sklearn.ensemble import IsolationForest
import pandas as pd
from app.db import get_engine
from app.alerts import slack_alert

def detect_revenue_anomalies():
    engine = get_engine()

    # Load last 30 days of hourly revenue for training context
    df = pd.read_sql("""
        SELECT window_start, total_revenue, order_count,
               avg_order_value, refund_rate
        FROM mart_revenue_hourly
        WHERE window_start >= now() - interval '30 days'
        ORDER BY window_start
    """, engine)

    # Train Isolation Forest on historical data
    # contamination=0.02 means we expect ~2% of hours to be anomalous
    clf = IsolationForest(
        n_estimators=100,
        contamination=0.02,
        random_state=42
    )
    features = df[['total_revenue', 'order_count', 'avg_order_value', 'refund_rate']]
    df['anomaly_score'] = clf.fit_predict(features)
    df['raw_score'] = clf.score_samples(features)

    # Flag rows where the model predicts anomaly (-1)
    anomalies = df[df['anomaly_score'] == -1]

    for _, row in anomalies.iterrows():
        # Write to anomaly_flags table
        write_anomaly_flag(row, engine)

        # Fire Slack alert (only once per window — idempotent check)
        if not already_alerted(row['window_start'], engine):
            slack_alert(
                f"Revenue anomaly detected at {row['window_start']} — "
                f"score: {row['raw_score']:.3f}, "
                f"actual revenue: €{row['total_revenue']:,.2f}"
            )

if __name__ == "__main__":
    detect_revenue_anomalies()
```

**Why Isolation Forest?** It's unsupervised — you don't need labelled anomaly data, which you never have when building from scratch. It handles multivariate anomalies well (a combination of low revenue AND high refund rate is more suspicious than either alone). And it's explainable enough to describe in an interview without hand-waving. Full rationale: [`docs/adr/003-isolation-forest.md`](docs/adr/003-isolation-forest.md)

---

## Grafana dashboard

The dashboard at `http://localhost:3000` shows:

| Panel | Refresh | Query source |
|---|---|---|
| Live conversion funnel | 30s | `mart_conversion_funnel` |
| Revenue per hour (last 48h) | 1m | `mart_revenue_hourly` |
| Revenue by product category | 5m | `mart_revenue_by_category` |
| Anomaly flags timeline | 1m | `anomaly_flags` |
| Active Kafka consumer lag | 15s | Kafka JMX via Prometheus |
| dbt test pass/fail status | 5m | `dbt_test_results` metadata table |

The dashboard JSON is version-controlled in `grafana/dashboards/`. Reviewing the diff in a PR is how you catch accidental metric renames before they break production dashboards.

---

## Kafka topic design

```
Topic: clickstream.raw
  Partitions: 6
  Retention: 7 days
  Key: session_id  (ensures all events from a session go to the same partition → ordered processing)

Topic: orders.raw
  Partitions: 3
  Retention: 30 days
  Key: order_id

Topic: refunds.raw
  Partitions: 3
  Retention: 30 days
  Key: order_id
```

Partition count is a deliberate choice: 6 partitions on `clickstream.raw` means you can run up to 6 consumer instances in parallel (one per partition). Running more instances than partitions is wasteful — the extras sit idle. Full rationale: [`docs/adr/001-kafka-partition-strategy.md`](docs/adr/001-kafka-partition-strategy.md)

---

## Idempotency

Every raw table has a `kafka_offset` column with a unique constraint. The consumer runs:

```python
INSERT INTO raw_orders (..., kafka_offset)
VALUES (..., %s)
ON CONFLICT (kafka_offset) DO NOTHING;
```

This means replaying a Kafka topic from an earlier offset — for backfill or recovery — never creates duplicates. The pipeline is safe to re-run.

dbt models use `{{ config(materialized='incremental', unique_key='order_id') }}` where appropriate. Re-running dbt updates existing rows rather than appending duplicates.

---

## Project structure

```
stream-lens/
├── producer/
│   └── generate_events.py         # Faker-based event generator, ~100 events/sec
├── consumer/
│   ├── ingest.py                  # Kafka consumer group, writes to raw tables
│   └── schema_registry.py        # Validates event schema before writing
├── dbt/                           # (see dbt project structure above)
├── anomaly_detector/
│   ├── detect.py                  # Isolation Forest detection job
│   └── alerts.py                  # Slack webhook delivery
├── airflow/
│   └── dags/
│       └── pipeline_dag.py        # Orchestrates: dbt run → dbt test → detect anomalies
├── grafana/
│   └── dashboards/
│       └── ecommerce.json         # Version-controlled dashboard definition
├── tests/
│   ├── test_consumer_idempotency.py
│   ├── test_anomaly_detector.py
│   └── test_dbt_models.py         # Runs dbt tests in CI
├── docs/
│   └── adr/
│       ├── 001-kafka-partition-strategy.md
│       ├── 002-dbt-over-sqlalchemy.md
│       └── 003-isolation-forest.md
├── docker-compose.yml
└── README.md
```

---

## Running tests

```bash
# Unit tests
pytest tests/ -v --cov=consumer --cov=anomaly_detector

# dbt data quality tests (requires running Postgres)
dbt test

# Full integration test (starts Kafka, produces 1000 events, checks mart counts)
pytest tests/test_integration.py -v --timeout=60
```

---

## Design decisions

**1. dbt over raw SQLAlchemy for transformations**
dbt gives you version-controlled, testable, documented SQL. Every model is a SQL file in Git. Every column has a test. Every model has a description. With raw SQLAlchemy scripts, none of that exists by default — you'd build it yourself and do it worse. Full rationale: [`docs/adr/002-dbt-over-sqlalchemy.md`](docs/adr/002-dbt-over-sqlalchemy.md)

**2. Kafka over direct Postgres writes from the producer**
The producer generates bursts of events (flash sales, marketing campaigns). Writing directly to Postgres during a burst can cause connection exhaustion and lock contention. Kafka absorbs the burst; the consumer processes at a steady rate. The topic also acts as a replayable audit log — every raw event is preserved for 7 days.

**3. Isolation Forest over a rules-based threshold**
A static threshold ("alert if revenue drops >30%") breaks at every seasonal pattern — Christmas, Black Friday, Monday mornings. Isolation Forest learns the normal distribution from 30 days of history and adapts. The trade-off is that it needs enough history to be meaningful — on day 1, it's not useful. That's acceptable for this use case.

---

## What I learned building this

The hardest part was idempotency — making the pipeline safe to replay. Every Kafka tutorial shows you how to consume messages. None of them tell you what happens when your consumer crashes halfway through a batch and you restart it: you get duplicate writes unless you've designed against it from the start.

The second hardest thing was realising that dbt tests are not optional. The first version of this project had no dbt tests. A schema change in the producer broke the staging model silently, and the conversion funnel showed 0% for two hours before I noticed. Data quality checks are the unit tests of data engineering.

---

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Message broker | Apache Kafka 3.7 | Industry standard for event streaming; replayable, partitioned, durable |
| Transformations | dbt 1.8 + PostgreSQL | Version-controlled SQL with built-in testing and lineage |
| Anomaly detection | scikit-learn (Isolation Forest) | Unsupervised, no labelled data needed, explainable |
| Orchestration | Apache Airflow 2.9 | Industry standard; DAG-based dependencies beat cron for multi-step pipelines |
| Visualisation | Grafana 10.4 | Best-in-class for time-series dashboards; version-controllable JSON |
| Alerting | Slack webhooks | Simple, reliable, zero infra overhead |
| Event generation | Faker | Realistic synthetic data without privacy concerns |
| Testing | pytest + dbt test | Unit tests for Python; schema tests for SQL models |

---

## Author

Built by [Chirantha K M](https://github.com/chiranthakm-Dev) · CSE graduate · Open to backend and systems engineering roles in the Netherlands.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat-square&logo=linkedin)](https://www.linkedin.com/in/chiranthkm/)
[![Email](https://img.shields.io/badge/Email-say%20hi-EA4335?style=flat-square&logo=gmail)](mailto:chirantha.km88@gmail.com)

---

## License

MIT
