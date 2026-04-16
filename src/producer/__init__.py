"""
Event Producer Service for Real-Time E-Commerce Analytics Pipeline.

This service generates realistic e-commerce events and publishes them to Kafka/Redpanda.
Supports multiple event types with configurable throughput and anomaly injection.
"""

from .producer import main

__all__ = ["main"]