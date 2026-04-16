-- Initialize database schema for Real-Time E-Commerce Analytics Pipeline

-- Create database (if not exists)
-- Note: This is handled by POSTGRES_DB environment variable

-- Create schemas
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS metrics;

-- Raw events table (exactly matching producer schema)
CREATE TABLE IF NOT EXISTS raw.events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    product_id VARCHAR(100),
    category VARCHAR(100),
    price DECIMAL(10,2),
    quantity INTEGER,
    order_id VARCHAR(100),
    payment_method VARCHAR(50),
    shipping_address JSONB,
    billing_address JSONB,
    user_agent TEXT,
    ip_address INET,
    referrer_url TEXT,
    campaign_id VARCHAR(100),
    discount_code VARCHAR(50),
    discount_amount DECIMAL(10,2),
    tax_amount DECIMAL(10,2),
    shipping_cost DECIMAL(10,2),
    total_amount DECIMAL(10,2),
    currency VARCHAR(3) DEFAULT 'USD',
    status VARCHAR(50),
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for raw events
CREATE INDEX IF NOT EXISTS idx_raw_events_timestamp ON raw.events (timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_events_event_type ON raw.events (event_type);
CREATE INDEX IF NOT EXISTS idx_raw_events_user_id ON raw.events (user_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_session_id ON raw.events (session_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_product_id ON raw.events (product_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_order_id ON raw.events (order_id);

-- Anomaly detection results table
CREATE TABLE IF NOT EXISTS raw.anomalies (
    anomaly_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES raw.events(event_id),
    anomaly_score DECIMAL(10,6) NOT NULL,
    anomaly_type VARCHAR(50) NOT NULL,
    detection_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    features JSONB,
    threshold DECIMAL(10,6),
    model_version VARCHAR(50),
    metadata JSONB
);

-- Create indexes for anomalies
CREATE INDEX IF NOT EXISTS idx_anomalies_detection_timestamp ON raw.anomalies (detection_timestamp);
CREATE INDEX IF NOT EXISTS idx_anomalies_anomaly_score ON raw.anomalies (anomaly_score DESC);
CREATE INDEX IF NOT EXISTS idx_anomalies_event_id ON raw.anomalies (event_id);

-- Processed events table (for idempotent processing)
CREATE TABLE IF NOT EXISTS staging.processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processor_version VARCHAR(50),
    batch_id UUID,
    processing_status VARCHAR(20) DEFAULT 'completed'
);

-- Create index for processed events
CREATE INDEX IF NOT EXISTS idx_processed_events_processed_at ON staging.processed_events (processed_at);

-- Consumer metrics table
CREATE TABLE IF NOT EXISTS metrics.consumer_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    events_processed INTEGER DEFAULT 0,
    events_failed INTEGER DEFAULT 0,
    batch_size INTEGER,
    processing_time_ms INTEGER,
    lag_messages INTEGER,
    lag_seconds INTEGER
);

-- Producer metrics table
CREATE TABLE IF NOT EXISTS metrics.producer_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    events_sent INTEGER DEFAULT 0,
    events_failed INTEGER DEFAULT 0,
    throughput_per_second DECIMAL(10,2),
    avg_event_size_bytes INTEGER
);

-- Anomaly metrics table
CREATE TABLE IF NOT EXISTS metrics.anomaly_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    total_events_analyzed INTEGER DEFAULT 0,
    anomalies_detected INTEGER DEFAULT 0,
    anomaly_rate DECIMAL(5,4),
    avg_anomaly_score DECIMAL(10,6),
    model_accuracy DECIMAL(5,4)
);

-- Create indexes for metrics tables
CREATE INDEX IF NOT EXISTS idx_consumer_metrics_timestamp ON metrics.consumer_metrics (timestamp);
CREATE INDEX IF NOT EXISTS idx_producer_metrics_timestamp ON metrics.producer_metrics (timestamp);
CREATE INDEX IF NOT EXISTS idx_anomaly_metrics_timestamp ON metrics.anomaly_metrics (timestamp);

-- Grant permissions (adjust as needed for your setup)
-- GRANT USAGE ON SCHEMA raw TO analytics_user;
-- GRANT USAGE ON SCHEMA staging TO analytics_user;
-- GRANT USAGE ON SCHEMA marts TO analytics_user;
-- GRANT USAGE ON SCHEMA metrics TO analytics_user;

-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA raw TO analytics_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA staging TO analytics_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA marts TO analytics_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA metrics TO analytics_user;