# Getting Started Guide

## Prerequisites

- **Docker** (v20.10+) and **Docker Compose** (v2+)
  - macOS: [Docker Desktop](https://www.docker.com/products/docker-desktop)
  - Linux: [Docker Engine](https://docs.docker.com/engine/install/)
  
- **RAM:** Minimum 4 GB available (recommended 8 GB)
- **Disk:** 5 GB free space initially

- **Optional for development:**
  - Python 3.9+ (if running services outside Docker)
  - dbt-core 1.5+
  - PostgreSQL client tools (`psql`)

---

## 1. Clone & Setup

```bash
# Clone repository
git clone <repository-url>
cd real-time-ecommerce-analytics

# Verify Docker is running
docker --version
docker compose version

# Check available RAM
free -h  # Linux
vm_stat | grep "Pages free"  # macOS
```

---

## 2. One-Command Startup

```bash
# Start entire pipeline (all 6 layers)
docker compose up

# Expected output (first run takes 30-45 seconds):
# ✓ Redpanda (Kafka)
# ✓ PostgreSQL
# ✓ Event Producer
# ✓ Python Consumer
# ✓ dbt Transformations
# ✓ Anomaly Detection
# ✓ Grafana
```

**Wait until you see:**
```
grafana_1  | t=2026-04-16T14:30:00Z lvl=info msg="Server started" logger=server port=3000
```

---

## 3. Access Services

Open these URLs in your browser:

| Service | URL | Purpose |
|---------|-----|---------|
| **Grafana** | http://localhost:3000 | Dashboard |
| **Redpanda** | http://localhost:8080 | Kafka UI |
| **Prometheus** | http://localhost:9090 | Metrics |

### Grafana Login
- User: `admin`
- Password: `admin`
- Change password on first login

---

## 4. Explore the Dashboard

In Grafana (http://localhost:3000):

1. **Home** → Look for **"Real-Time E-Commerce Analytics"** dashboard
2. **Panels visible:**
   - Conversion Funnel (% of users reaching each step)
   - Revenue Over Time (hourly breakdown by category)
   - Cohort Retention Heatmap (user retention patterns)
   - Data Quality (dbt test status)

3. **Features to try:**
   - Hover over anomalies (red dots on Revenue chart)
   - Click on categories to filter
   - Change time range (upper right)

---

## 5. Verify Each Layer

### Layer 1: Event Generation
```bash
# Check if events are being generated
docker logs real-time-ecommerce-analytics-producer-1 | tail -20

# Expected:
# Generated event: {event_id: ..., user_id: usr_4821, revenue: 49.99, ts: ...}
```

### Layer 2: Kafka / Redpanda
```bash
# Check topics
docker exec redpanda-1 rpk topic list

# Expected output:
# NAME                     PARTITIONS  REPLICATION-FACTOR
# page_views               2           1
# cart_events              2           1
# purchases                2           1

# Inspect messages
docker exec redpanda-1 rpk topic consume purchases --num 1
```

### Layer 3: Consumer
```bash
# Check consumer logs
docker logs real-time-ecommerce-analytics-consumer-1 | tail -20

# Check PostgreSQL for inserted events
docker exec postgres-1 psql -U postgres -d analytics -c "SELECT COUNT(*) FROM raw_events;"
```

### Layer 4: dbt Transformations
```bash
# Run dbt models manually (optional, runs hourly by default)
docker exec dbt-1 dbt run

# Check dbt tests
docker exec dbt-1 dbt test

# View model documentation
docker exec dbt-1 dbt docs generate
# Open http://localhost:8000 (if enabled)
```

### Layer 5: Anomaly Detection
```bash
# Check detector logs
docker logs real-time-ecommerce-analytics-anomaly-detector-1 | tail -20

# Check anomalies detected
docker exec postgres-1 psql -U postgres -d analytics -c "SELECT COUNT(*) FROM anomalies WHERE detected_at > NOW() - INTERVAL '1 hour';"
```

### Layer 6: Grafana
```bash
# Grafana should load automatically
# URL: http://localhost:3000
# Check logs if issues
docker logs real-time-ecommerce-analytics-grafana-1 | tail -20
```

---

## 6. Database Exploration

```bash
# Connect to PostgreSQL
docker exec -it postgres-1 psql -U postgres -d analytics

# Common queries
SELECT COUNT(*) FROM raw_events;  -- Total events ingested
SELECT COUNT(*) FROM dead_letter;  -- Validation errors
SELECT COUNT(*) FROM anomalies;  -- Flagged anomalies
SELECT COUNT(*) FROM fct_purchases;  -- Business fact table

# Inspect schema
\dt  -- List tables
\d fct_purchases  -- Describe table structure
\di  -- List indexes

# Exit psql
\q
```

---

## 7. Generate Load Test Data

```bash
# Optional: Generate high-throughput test
# Increases event generation from 300/sec to 500/sec

# Modify producer config (edit .env or docker-compose.yml)
# PRODUCER_THROUGHPUT=500

docker compose up -d producer  # Restart producer with new config

# Monitor in Grafana
# Watch for: 500 events/sec sustained
#           Consumer lag < 5 seconds
#           Revenue chart updating in real-time
```

---

## 8. Understanding File Structure

```
project/
├── README.md                  ← Start here (overview)
├── ARCHITECTURE.md            ← Deep dive into each layer
├── DATA_FLOW.md              ← Event lifecycle & scenarios
├── GETTING_STARTED.md        ← This file

├── docker-compose.yml        ← All services defined here
├── .env                       ← Configuration (secrets, throughput)

├── src/
│   ├── producer/             ← Layer 1: Event generation
│   ├── consumer/             ← Layer 3: Kafka → PostgreSQL
│   ├── anomaly_detection/    ← Layer 5: ML model & metrics
│   └── utils/

├── dbt/                       ← Layer 4: Transformations & tests
│   ├── models/
│   │   ├── staging/          ← Type casting, filtering
│   │   ├── marts/            ← Business logic
│   │   └── metrics/          ← Aggregations
│   └── schema.yml            ← Tests & properties

├── grafana/                   ← Layer 6: Dashboards
│   ├── provisioning/
│   │   ├── datasources/      ← PostgreSQL connection
│   │   └── dashboards/       ← Auto-loaded dashboard

└── scripts/
    ├── init_db.sql           ← Database schema
    ├── load_test.py          ← Benchmark script
    └── reset_pipeline.sh     ← Clean reset
```

---

## 9. Common Operations

### Stop the Pipeline
```bash
# Gracefully stop all services
docker compose down

# Stop but keep volumes (data persists)
docker compose down

# Remove everything including data
docker compose down -v
```

### View Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f producer

# Last 100 lines
docker compose logs --tail 100 consumer

# Follow + filter for errors
docker compose logs -f | grep ERROR
```

### Restart a Service
```bash
# Restart consumer (useful if crashed)
docker compose restart consumer

# Force rebuild and restart
docker compose up -d --build consumer
```

### Check Resource Usage
```bash
# See memory/CPU per container
docker stats

# See container details
docker ps

# Inspect specific container
docker inspect redpanda-1
```

---

## 10. Troubleshooting

### Problem: `docker compose up` Fails Immediately

**Symptom:** Error like "port 5432 already in use"

**Solution:**
```bash
# Stop any existing instances
docker compose down

# Kill all containers (more aggressive)
docker kill $(docker ps -q)

# Try again
docker compose up
```

### Problem: Consumer Lag Growing

**Symptom:** Dashboard shows "Consumer Lag > 30 seconds"

**Solution:**
```bash
# Check consumer logs for errors
docker logs real-time-ecommerce-analytics-consumer-1 | grep ERROR

# Restart consumer
docker compose restart consumer

# Check database lock contention
docker exec postgres-1 psql -U postgres -d analytics -c "SELECT * FROM pg_stat_activity;"
```

### Problem: Grafana Dashboard Not Loading

**Symptom:** Dashboard is blank or shows "No data"

**Solution:**
```bash
# Check datasource connection
# In Grafana: Configuration → Data Sources → PostgreSQL
# Click "Save & Test" to verify connection

# Check if database has data
docker exec postgres-1 psql -U postgres -d analytics -c "SELECT COUNT(*) FROM fct_purchases;"

# If empty, dbt may not have run yet
# Manually trigger dbt run
docker exec dbt-1 dbt run
docker exec dbt-1 dbt test
```

### Problem: Out of Memory

**Symptom:** Services crash with OOM errors

**Solution:**
```bash
# Increase Docker Desktop memory allocation
# Docker Desktop → Preferences → Resources → Memory (increase to 8-10 GB)

# Or reduce producer throughput
# Edit .env: PRODUCER_THROUGHPUT=300  (from 500)
```

### Problem: PostgreSQL Connection Refused

**Symptom:** Consumer crashes with "connection refused to postgres:5432"

**Solution:**
```bash
# Check if PostgreSQL is running
docker compose ps

# Restart PostgreSQL
docker compose restart postgres

# Wait 5 seconds and restart consumer
docker compose restart consumer
```

---

## 11. Next Steps After Startup

1. **Read the README** for architecture overview
2. **Explore ARCHITECTURE.md** for deep dives on each layer
3. **Check DATA_FLOW.md** to understand event-to-dashboard journey
4. **Browse dbt models** in `dbt/models/` to see transformations
5. **Modify producer** in `src/producer/main.py` to adjust anomaly injection
6. **Write custom dbt test** in `dbt/tests/` to practice
7. **Create new Grafana panel** to visualize custom metric
8. **Deploy to cloud** (Railway/Render) to get live URL

---

## 12. Performance Benchmarking

### Run Load Test

```bash
# Terminal 1: Keep pipeline running
docker compose up

# Terminal 2: Run load test
cd scripts
python load_test.py --duration 120 --throughput 500

# Expected results (should see in terminal):
# ✓ 500 events/second sustained
# ✓ Consumer lag: < 5 seconds
# ✓ P95 latency: < 1.5 seconds
```

### Monitor During Load Test

```bash
# In another terminal, watch Grafana
# http://localhost:3000
# Charts should show:
# - Revenue increasing
# - Consumer lag stable
# - Anomalies being detected
```

---

## 13. Development Tips

### Adding a New Field to Events

1. Update Pydantic schema in `src/consumer/models.py`
2. Update event generator in `src/producer/schemas.py`
3. Add new column to `raw_events` table (migrations not automated)
4. Update dbt staging models to handle new field
5. Restart producer & consumer

### Creating a New dbt Model

```bash
# Inside dbt container
docker exec dbt-1 dbt run --select my_new_model

# Test it
docker exec dbt-1 dbt test --select my_new_model

# Generate documentation
docker exec dbt-1 dbt docs generate
```

### Debugging Anomaly Detection

```bash
# Connect to database
docker exec -it postgres-1 psql -U postgres -d analytics

# Check recent anomalies
SELECT event_id, anomaly_score, detected_at 
FROM anomalies 
WHERE detected_at > NOW() - INTERVAL '10 minutes' 
ORDER BY detected_at DESC;

# Inspect corresponding events
SELECT * FROM fct_purchases 
WHERE event_id IN (...);  -- Copy event_ids from above
```

---

## 14. Shutting Down Gracefully

```bash
# Option 1: Foreground mode (Ctrl+C to stop)
docker compose up
# Ctrl+C

# Option 2: Background mode
docker compose up -d
docker compose down  # Later, when ready to stop

# Option 3: Keep data, just stop services
docker compose stop

# Option 4: Full cleanup (removes data)
docker compose down -v
```

---

## 15. Useful Commands Reference

```bash
# View all services status
docker compose ps

# Stream live logs
docker compose logs -f

# Execute command in container
docker exec <container> <command>

# Example: PostgreSQL query
docker exec postgres-1 psql -U postgres -d analytics -c "SELECT * FROM fct_purchases LIMIT 5;"

# Open bash shell in container
docker exec -it consumer-1 /bin/bash

# Restart everything
docker compose restart

# Rebuild images
docker compose build

# View volumes
docker volume ls

# Remove unused resources
docker system prune
```

---

## 16. When Something Goes Wrong

**Golden rules:**
1. **Check logs first:** `docker compose logs -f | grep ERROR`
2. **Restart the service:** `docker compose restart <service>`
3. **If still broken, restart everything:** `docker compose down && docker compose up`
4. **Check PostgreSQL:** `SELECT COUNT(*) FROM raw_events;` (should grow)
5. **Check Grafana:** Dashboard should show live data
6. **Read ARCHITECTURE.md** for deep understanding

---

## 17. Support & Documentation

- **README.md** — Overview & architecture
- **ARCHITECTURE.md** — Detailed design of each layer
- **DATA_FLOW.md** — Event journey & failure scenarios
- **Code comments** — Most Python/SQL files are extensively documented
- **dbt schema.yml** — dbt model documentation

---

**You're all set!** 🚀

Start with `docker compose up` and explore the dashboard at http://localhost:3000

Questions? Check ARCHITECTURE.md for deep dives, or review the code comments in each service.
