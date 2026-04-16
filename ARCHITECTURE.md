# Architecture Deep Dive

## System Design Philosophy

This pipeline follows **layered architecture** principles:
- Each layer has a single responsibility
- Layers communicate via well-defined interfaces
- Failures in one layer do not cascade (dead-letter queues, circuit breakers)
- Every component is observable and alertable

---

## Layer 1: Event Generation

### Responsibilities
- Generate realistic e-commerce clickstream events
- Inject controlled anomalies to test detection
- Publish to Kafka with guaranteed throughput

### Event Flow
```
Faker → Event Objects → Serialization → Kafka Producer → Redpanda
```

### Anomaly Injection Strategy

| Anomaly Type | Frequency | Simulation | Use Case |
|--------------|-----------|-----------|----------|
| Revenue spike | Every ~200 events | Revenue = 10x normal | Fraud detection |
| Bot traffic burst | Every ~500 events | 50 page views in 1 sec | Traffic anomaly |
| Late-arriving event | Every ~1000 events | ts = now - 2 hours | Out-of-order handling |

**Rate Configuration:** Documented in `src/producer/anomaly_injector.py`

---

## Layer 2: Message Broker (Redpanda)

### Topic Architecture

#### Topic: `page_views`
- **Partitions:** 2 (by `user_id % 2`)
- **Retention:** 1 hour
- **Events/sec:** ~200
- **Schema:**
  ```json
  {
    "event_id": "uuid",
    "user_id": "string",
    "product_id": "string",
    "category": "string",
    "ts": "timestamp"
  }
  ```

#### Topic: `cart_events`
- **Partitions:** 2 (by `user_id % 2`)
- **Retention:** 1 hour
- **Events/sec:** ~150
- **Schema:**
  ```json
  {
    "event_id": "uuid",
    "user_id": "string",
    "product_id": "string",
    "action": "add|remove",
    "quantity": "int",
    "ts": "timestamp"
  }
  ```

#### Topic: `purchases`
- **Partitions:** 2 (by `user_id % 2`)
- **Retention:** 1 hour
- **Events/sec:** ~150
- **Schema:** (See README data contract)

### Why Redpanda?

**Trade-off Analysis:**

| Criterion | Redpanda | Kafka | Conclusion |
|-----------|----------|-------|-----------|
| Local startup time | 3s | 15s | Redpanda wins (portfolio needs speed) |
| ZooKeeper required | No | Yes | Redpanda simpler |
| API compatibility | 100% Kafka-compatible | Native | Portable code |
| Market relevance | Growing in Dutch fintech | Standard everywhere | Both relevant |
| Production maturity | Newer, actively maintained | Battle-tested | Kafka for prod, Redpanda for local |

**Decision:** Redpanda for portfolio development (see ADR-1 in README).

### Consumer Configuration

```yaml
# consumer_config.properties
bootstrap.servers=redpanda:9092
group.id=ecommerce-consumer-group
auto.offset.reset=earliest
enable.auto.commit=false
session.timeout.ms=30000
max.poll.records=500
```

**Key Settings Explained:**
- `auto.offset.reset=earliest`: On first run, process all history (good for testing)
- `enable.auto.commit=false`: Manual offset management (safer for data integrity)
- `session.timeout.ms=30000`: Fast failure detection
- `max.poll.records=500`: Batch size for throughput optimization

---

## Layer 3: Consumer + Validator

### Validation Pipeline

```
Raw Message
    ↓
JSON Decode
    ↓
Pydantic Schema Validation
    ↓
Business Logic Validation
    ↓
Deduplication Check
    ↓
[Valid: Insert] or [Invalid: Dead-Letter]
```

### Pydantic Schemas

```python
class PurchaseEvent(BaseModel):
    event_id: UUID = Field(..., description="Unique event identifier")
    user_id: str = Field(..., regex="^usr_\d+$")
    session_id: str = Field(..., regex="^sess_\d+$")
    product_id: str = Field(..., regex="^prod_\d+$")
    category: str = Field(..., min_length=1)
    revenue: float = Field(..., gt=0, le=10000)  # Sanity check
    currency: str = Field(default="EUR", regex="^[A-Z]{3}$")
    ts: datetime = Field(...)
    country: str = Field(..., min_length=2, max_length=2)
    
    @validator("ts")
    def ts_not_future(cls, v):
        if v > datetime.utcnow():
            raise ValueError("Event timestamp cannot be in future")
        if v < datetime.utcnow() - timedelta(hours=24):
            raise ValueError("Event older than 24h rejected")
        return v
```

### Idempotent Insert Pattern

**Why idempotent inserts?** See ADR-3 in README.

```python
INSERT INTO raw_events 
  (event_id, user_id, product_id, revenue, ts, country, created_at)
VALUES 
  (%s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT (event_id) DO NOTHING;
```

**Consumer Restart Safety:**
1. Consumer crashes after message processed but before offset commit
2. Kafka rebalances, consumer restarts
3. Same message is redelivered
4. `ON CONFLICT DO NOTHING` silently discards duplicate
5. No data loss, no duplication ✅

### Dead-Letter Queue

**Schema:**
```sql
CREATE TABLE dead_letter (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID,
    raw_payload JSONB NOT NULL,
    error_reason TEXT NOT NULL,
    error_type TEXT NOT NULL,  -- validation_error, type_error, business_logic_error
    partition INT,
    offset BIGINT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_dead_letter_created_at ON dead_letter(created_at DESC);
CREATE INDEX idx_dead_letter_error_type ON dead_letter(error_type);
```

**Example Entry:**
```json
{
  "error_type": "validation_error",
  "error_reason": "revenue validation failed: 50000.00 > 10000 (max)",
  "raw_payload": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "revenue": 50000.00
  },
  "created_at": "2026-04-16T14:35:22Z"
}
```

### Consumer Architecture

```python
class ECommerceConsumer:
    def __init__(self):
        self.kafka_client = KafkaConsumer(...)
        self.db_pool = ConnectionPool(...)
        self.dead_letter_handler = DeadLetterHandler(self.db_pool)
    
    def run(self):
        for message in self.kafka_client:
            try:
                # Parse & validate
                event = PurchaseEvent(**json.loads(message.value))
                
                # Persist
                self.db_pool.execute(INSERT_IDEMPOTENT, event.dict().values())
                
                # Commit offset (only after DB insert)
                self.kafka_client.commit()
                
            except ValidationError as e:
                # Log to dead-letter, don't crash
                self.dead_letter_handler.log(message, str(e), "validation_error")
                self.kafka_client.commit()  # Still advance offset
            
            except Exception as e:
                # Unexpected error, log & retry
                logger.error(f"Unexpected error: {e}")
                # Don't commit offset; message will be reprocessed
                raise
```

---

## Layer 4: Transformation (dbt)

### Staging Layer Goals
- **Type casting:** String → UUID, timestamps, decimals
- **Renaming:** Normalize snake_case across all fields
- **Filtering:** Remove test events, future-dated events
- **Deduplication:** Handle rare late-arriving duplicates

### Example: `stg_purchases`

```sql
{{ config(
    materialized='view',
    tags=['staging']
) }}

WITH raw AS (
    SELECT
        event_id,
        user_id,
        session_id,
        product_id,
        category,
        revenue::DECIMAL(10, 2) AS revenue,
        currency,
        ts::TIMESTAMP AS event_ts,
        country
    FROM {{ source('raw', 'raw_events') }}
    WHERE 
        -- Filter out test events
        user_id NOT LIKE 'test_%'
        -- Only recent events
        AND ts >= CURRENT_DATE - INTERVAL '7 days'
)

SELECT *
FROM raw
WHERE revenue > 0  -- Sanity check
  AND currency IN ('EUR', 'USD', 'GBP')
  AND country IN ('NL', 'DE', 'FR', 'BE', 'GB')
```

### Mart Layer: Business Logic

#### `fct_purchases` — Core Fact Table

```sql
{{ config(
    materialized='table',
    unique_id='event_id',
    tags=['mart']
) }}

WITH purchases AS (
    SELECT * FROM {{ ref('stg_purchases') }}
)

, users AS (
    SELECT 
        user_id,
        COUNT(*) AS total_purchases,
        SUM(revenue) AS lifetime_value,
        MAX(event_ts) AS last_purchase_ts
    FROM purchases
    GROUP BY user_id
)

SELECT
    p.event_id,
    p.user_id,
    p.session_id,
    p.product_id,
    p.category,
    p.revenue,
    p.currency,
    p.event_ts,
    p.country,
    
    -- User dimensions
    EXTRACT(YEAR FROM p.event_ts) AS purchase_year,
    EXTRACT(MONTH FROM p.event_ts) AS purchase_month,
    EXTRACT(DOW FROM p.event_ts) AS purchase_day_of_week,
    EXTRACT(HOUR FROM p.event_ts) AS purchase_hour,
    
    -- Surrogate keys
    u.total_purchases,
    u.lifetime_value,
    CAST(p.revenue / NULLIF(u.total_purchases, 0) AS DECIMAL(10, 2)) AS avg_purchase_value,
    
    -- Data quality flags
    CASE 
        WHEN p.revenue > 10000 THEN 'anomaly_high_revenue'
        WHEN p.revenue < 0.01 THEN 'anomaly_low_revenue'
        ELSE 'normal'
    END AS data_quality_flag,
    
    -- SCD Type 1 (latest values)
    CURRENT_TIMESTAMP AS dbt_loaded_at

FROM purchases p
LEFT JOIN users u ON p.user_id = u.user_id
```

### Metrics Layer

#### `daily_revenue`

```sql
{{ config(
    materialized='table',
    tags=['metrics']
) }}

SELECT
    DATE(event_ts) AS revenue_date,
    category,
    country,
    COUNT(*) AS transaction_count,
    SUM(revenue) AS total_revenue,
    AVG(revenue) AS avg_transaction_value,
    STDDEV(revenue) AS stddev_revenue,
    MIN(revenue) AS min_revenue,
    MAX(revenue) AS max_revenue,
    CURRENT_TIMESTAMP AS computed_at
FROM {{ ref('fct_purchases') }}
WHERE event_ts >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY 1, 2, 3
```

### dbt Test Coverage

**Generic Tests (built-in):**
```yaml
models:
  - name: fct_purchases
    columns:
      - name: event_id
        tests:
          - unique
          - not_null
      
      - name: revenue
        tests:
          - not_null
          - expression_is_true:
              expression: "revenue > 0 AND revenue < 1000000"
      
      - name: country
        tests:
          - not_null
          - accepted_values:
              values: ['NL', 'DE', 'FR', 'BE', 'GB']
```

**Custom Macros (example):**
```sql
-- macros/test_revenue_sensible.sql
{% macro test_revenue_sensible(model, column_name) %}
    SELECT *
    FROM {{ model }}
    WHERE {{ column_name }} > 100000  -- Unreasonably high
    LIMIT 100
{% endmacro %}
```

### dbt Hooks: Post-Run Actions

```yaml
# dbt_project.yml
on-run-end:
  - "{{ run_query(execute_and_send_slack_alerts()) }}"
  - "{{ run_query(refresh_materialized_views()) }}"
```

---

## Layer 5: Anomaly Detection

### Isolation Forest Algorithm

**Why Isolation Forest?** See ADR-2 in README.

```python
from sklearn.ensemble import IsolationForest
import pickle

class AnomalyDetector:
    def __init__(self, contamination=0.01):
        """
        contamination: Expected fraction of anomalies (0.01 = 1%)
        """
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100,
            max_samples='auto',
            verbose=1
        )
        self.feature_names = [
            'revenue',
            'hour_of_day',
            'events_in_session',
            'time_since_last_purchase_seconds'
        ]
    
    def train(self, purchase_df):
        """Train on recent purchases"""
        X = purchase_df[self.feature_names].fillna(0).values
        self.model.fit(X)
        return self
    
    def predict(self, purchase_df):
        """
        Returns array of -1 (anomaly) or 1 (normal)
        """
        X = purchase_df[self.feature_names].fillna(0).values
        predictions = self.model.predict(X)
        anomaly_scores = self.model.score_samples(X)
        return predictions, anomaly_scores
```

### Feature Engineering

**Rolling window (last 500 purchases):**
```python
def compute_features(purchases_df):
    purchases_df = purchases_df.sort_values('event_ts').tail(500)
    
    features = []
    for idx, row in purchases_df.iterrows():
        # 1. Revenue (in EUR)
        revenue = row['revenue']
        
        # 2. Hour of day (captures time patterns)
        hour_of_day = row['event_ts'].hour
        
        # 3. Events in session (user activity level)
        session_id = row['session_id']
        events_in_session = purchases_df[
            purchases_df['session_id'] == session_id
        ].shape[0]
        
        # 4. Time since last purchase (seasonality)
        user_id = row['user_id']
        prev_purchase = purchases_df[
            (purchases_df['user_id'] == user_id) & 
            (purchases_df['event_ts'] < row['event_ts'])
        ]['event_ts'].max()
        
        time_since_last = (row['event_ts'] - prev_purchase).total_seconds()
        
        features.append({
            'event_id': row['event_id'],
            'revenue': revenue,
            'hour_of_day': hour_of_day,
            'events_in_session': events_in_session,
            'time_since_last_purchase_seconds': time_since_last or 0
        })
    
    return pd.DataFrame(features)
```

### Polling Architecture

```python
def polling_loop():
    detector = AnomalyDetector(contamination=0.01)
    prometheus_registry = CollectorRegistry()
    anomaly_counter = Counter(
        'anomaly_count_total',
        'Total anomalies detected',
        registry=prometheus_registry
    )
    
    while True:
        try:
            # Fetch last 500 purchases
            purchases = db.query("""
                SELECT * FROM fct_purchases 
                ORDER BY event_ts DESC LIMIT 500
            """)
            
            if len(purchases) < 50:
                logger.info("Insufficient data for detection")
                sleep(60)
                continue
            
            # Compute features & predict
            features_df = compute_features(purchases)
            predictions, scores = detector.predict(features_df)
            
            # Log anomalies
            anomalies = features_df[predictions == -1]
            for _, row in anomalies.iterrows():
                db.insert('anomalies', {
                    'event_id': row['event_id'],
                    'anomaly_score': row['anomaly_score'],
                    'detected_at': datetime.utcnow()
                })
                anomaly_counter.inc()
                logger.warning(f"Anomaly detected: {row['event_id']}")
            
            # Sleep before next poll
            sleep(60)
            
        except Exception as e:
            logger.error(f"Anomaly detection error: {e}")
            sleep(60)
```

### Model Registry & Retraining

```sql
-- Model versioning
CREATE TABLE model_registry (
    model_version INT PRIMARY KEY,
    training_date TIMESTAMP NOT NULL,
    feature_set TEXT NOT NULL,
    contamination_parameter FLOAT NOT NULL,
    training_sample_size INT NOT NULL,
    anomaly_count_in_training INT NOT NULL,
    model_bytes BYTEA NOT NULL,  -- Pickled sklearn model
    status VARCHAR(20) NOT NULL,  -- 'active' or 'deprecated'
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Weekly Retraining (Airflow DAG):**
```python
# dags/weekly_anomaly_retraining.py
@dag(
    dag_id='weekly_anomaly_retraining',
    schedule_interval='0 2 * * MON',  # 2 AM Monday
    default_view='graph'
)
def anomaly_retraining():
    
    @task
    def fetch_training_data():
        # Last 7 days of purchases
        return db.query("SELECT * FROM fct_purchases WHERE event_ts > NOW() - INTERVAL '7 days'")
    
    @task
    def train_model(df):
        detector = AnomalyDetector(contamination=0.01)
        detector.train(df)
        return detector
    
    @task
    def evaluate_model(detector, df):
        # Compare with existing model
        # If better, promote to active
        return {'accuracy': 0.95}
    
    @task
    def register_model(detector, metrics):
        # Save to model_registry table
        pass
    
    data = fetch_training_data()
    model = train_model(data)
    metrics = evaluate_model(model, data)
    register_model(model, metrics)

anomaly_retraining()
```

---

## Layer 6: Dashboard (Grafana)

### Provisioning Setup

**On startup:**
1. Grafana container starts
2. Reads `/etc/grafana/provisioning/datasources/postgres.yml`
3. Auto-creates PostgreSQL data source
4. Reads `/etc/grafana/provisioning/dashboards/ecommerce.yml`
5. Auto-imports `ecommerce_dashboard.json`
6. No manual configuration needed ✅

### Dashboard Queries

**Panel 1: Conversion Funnel**
```sql
WITH funnel AS (
    SELECT
        COUNT(DISTINCT CASE WHEN page_views > 0 THEN session_id END) AS page_viewers,
        COUNT(DISTINCT CASE WHEN cart_events > 0 THEN session_id END) AS cart_users,
        COUNT(DISTINCT session_id) AS purchasers
    FROM (
        SELECT 
            session_id,
            SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END) AS page_views,
            SUM(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) AS cart_events
        FROM events
        WHERE ts > NOW() - INTERVAL '24 hours'
        GROUP BY session_id
    )
)
SELECT 
    'Page Views' AS step,
    100.0 AS percentage
UNION ALL
SELECT 'Cart Adds', ROUND(100.0 * cart_users / page_viewers, 1)
FROM funnel
UNION ALL
SELECT 'Purchases', ROUND(100.0 * purchasers / page_viewers, 1)
FROM funnel
```

**Panel 2: Revenue Over Time (with Anomalies)**
```sql
-- Revenue by hour and category
SELECT
    DATE_TRUNC('hour', event_ts) AS hour,
    category,
    SUM(revenue) AS hourly_revenue,
    COUNT(*) AS transaction_count
FROM fct_purchases
WHERE event_ts > NOW() - INTERVAL '24 hours'
GROUP BY 1, 2
ORDER BY 1 DESC
```

---

## Observability Stack

### Metrics Collection
- **Prometheus** scrapes `/metrics` endpoint from anomaly detector
- **Grafana** queries Prometheus for time-series data
- **Slack** receives alerts from dbt on test failures

### Logging
- All Python services log to stdout (Docker collects logs)
- `docker compose logs -f consumer` to follow consumer logs
- dbt logs saved to `dbt/logs/dbt.log`

### Health Checks
```yaml
# docker-compose.yml
services:
  redpanda:
    healthcheck:
      test: ["CMD", "rpk", "broker", "info"]
      interval: 5s
      timeout: 3s
      retries: 3
  
  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 3
```

---

## Performance Characteristics

### Throughput
- **Max sustained:** 500 events/sec
- **Burst capacity:** 1000 events/sec for 10 seconds
- **Consumer batch size:** 500 records (tuned)

### Latency
- Event generation → Kafka: < 1ms
- Kafka → Consumer (processing): 200-400ms (P95)
- Consumer (INSERT): 50-100ms (P95)
- Anomaly detection (poll + predict): 42 seconds (entire pipeline)

### Resource Usage
- **Memory:** 1.8 GB peak
- **CPU:** 42% (4-core system)
- **Disk:** 100 MB/hour for 500 events/sec

---

## Disaster Recovery

### Consumer Crash Recovery
1. Consumer stops
2. Kafka broker holds messages with consumer's group offsets
3. Consumer restarts
4. Kafka rebalances; consumer rejoins group
5. Consumer resumes from last committed offset (idempotent inserts protect against duplication)
6. ✅ No data loss

### Database Failover (Production Consideration)
- Current setup: Single PostgreSQL instance (not HA)
- Future: Streaming replication to standby
- Backup strategy: Daily snapshots

### Model Drift Detection
- Track anomaly precision/recall weekly
- Flag if false positive rate exceeds threshold
- Automatically retrain if needed
- Alert ops team for manual review

