#!/bin/bash

# Kafka Topics Setup Script for Real-Time E-Commerce Analytics Pipeline
# This script creates the necessary Kafka topics for the event pipeline

set -e  # Exit on any error

# Configuration
REDPANDA_CONTAINER="ecommerce-redpanda"
TOPICS=(
    "page_views:2:1h"      # 2 partitions, 1 hour retention
    "cart_events:2:1h"     # 2 partitions, 1 hour retention
    "purchases:2:1h"       # 2 partitions, 1 hour retention
)

echo "Setting up Kafka topics for E-Commerce Analytics Pipeline..."

# Wait for Redpanda to be ready
echo "Waiting for Redpanda to be ready..."
timeout=60
while ! docker exec $REDPANDA_CONTAINER rpk cluster info >/dev/null 2>&1; do
    if [ $timeout -le 0 ]; then
        echo "ERROR: Redpanda is not ready after 60 seconds"
        exit 1
    fi
    echo "Waiting for Redpanda... ($timeout seconds remaining)"
    sleep 5
    timeout=$((timeout - 5))
done

echo "Redpanda is ready. Creating topics..."

# Create topics
for topic_config in "${TOPICS[@]}"; do
    IFS=':' read -r topic_name partitions retention <<< "$topic_config"

    echo "Creating topic: $topic_name (partitions: $partitions, retention: $retention)"

    # Create topic with specified configuration
    docker exec $REDPANDA_CONTAINER rpk topic create "$topic_name" \
        --partitions "$partitions" \
        --replicas 1 \
        --config retention.time="$retention" \
        --config cleanup.policy=delete \
        --config compression.type=snappy

    if [ $? -eq 0 ]; then
        echo "✅ Topic '$topic_name' created successfully"
    else
        echo "❌ Failed to create topic '$topic_name'"
        exit 1
    fi
done

echo ""
echo "Verifying topic creation..."
docker exec $REDPANDA_CONTAINER rpk topic list

echo ""
echo "Topic configuration:"
for topic_config in "${TOPICS[@]}"; do
    IFS=':' read -r topic_name partitions retention <<< "$topic_config"
    echo "Topic: $topic_name"
    docker exec $REDPANDA_CONTAINER rpk topic describe "$topic_name" | head -10
    echo "---"
done

echo ""
echo "✅ Kafka topics setup completed successfully!"
echo ""
echo "Test commands:"
echo "  # List topics"
echo "  docker exec $REDPANDA_CONTAINER rpk topic list"
echo ""
echo "  # Consume from purchases topic"
echo "  docker exec $REDPANDA_CONTAINER rpk topic consume purchases --num 1"
echo ""
echo "  # Check topic info"
echo "  docker exec $REDPANDA_CONTAINER rpk topic info purchases"