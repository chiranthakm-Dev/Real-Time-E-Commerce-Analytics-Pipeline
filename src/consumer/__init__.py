"""
Event Consumer Service for Real-Time E-Commerce Analytics Pipeline.

This service consumes events from Kafka, validates them, and stores them
in PostgreSQL with proper error handling and dead letter queues.
"""

from .consumer import main

__all__ = ["main"]