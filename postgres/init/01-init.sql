-- Initialize database for E-Commerce Analytics Pipeline

-- Create analytics schema
CREATE SCHEMA IF NOT EXISTS analytics;

-- Create raw_events table
CREATE TABLE IF NOT EXISTS analytics.raw_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create dead_letter table for failed events
CREATE TABLE IF NOT EXISTS analytics.dead_letter (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50),
    event_data JSONB,
    error_message TEXT,
    failed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    retry_count INTEGER DEFAULT 0
);

-- Create anomalies table
CREATE TABLE IF NOT EXISTS analytics.anomalies (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES analytics.raw_events(id),
    anomaly_score FLOAT NOT NULL,
    anomaly_type VARCHAR(100),
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    event_data JSONB
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_raw_events_type ON analytics.raw_events(event_type);
CREATE INDEX IF NOT EXISTS idx_raw_events_timestamp ON analytics.raw_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_anomalies_score ON analytics.anomalies(anomaly_score DESC);
CREATE INDEX IF NOT EXISTS idx_anomalies_timestamp ON analytics.anomalies(detected_at);

-- Grant permissions (adjust as needed)
GRANT ALL PRIVILEGES ON SCHEMA analytics TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA analytics TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA analytics TO postgres;