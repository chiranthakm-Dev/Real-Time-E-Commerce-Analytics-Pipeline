"""
Event Consumer Service.

Consumes events from Kafka topics, validates them using Pydantic schemas,
and stores valid events in PostgreSQL. Invalid events go to dead letter queue.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

import psycopg2
import psycopg2.extras
from confluent_kafka import Consumer, KafkaError, KafkaException

from ..shared import (
    setup_logging,
    get_logger,
    load_config,
    validate_config,
    create_postgres_connection_string,
    EventEnvelope,
    ProcessingResult,
    safe_json_dumps,
)


logger = get_logger(__name__)


class EventConsumer:
    """
    High-throughput Kafka consumer for e-commerce events.

    Features:
    - Batch processing for efficiency
    - Pydantic validation with detailed error reporting
    - Idempotent processing with deduplication
    - Dead letter queue for invalid events
    - Comprehensive metrics collection
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the event consumer.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.batch_size = config['consumer_batch_size']
        self.consumer_group = config['consumer_group_id']

        # Database connection
        self.db_conn_string = create_postgres_connection_string(config)
        self.db_conn = None

        # Kafka consumer (will be initialized)
        self.consumer = None

        # Metrics
        self.events_processed = 0
        self.events_failed = 0
        self.batches_processed = 0
        self.start_time = time.time()

        # Topics to consume
        self.topics = ['page_views', 'cart_events', 'purchases']

        logger.info(
            "Initialized event consumer",
            batch_size=self.batch_size,
            consumer_group=self.consumer_group,
            topics=self.topics
        )

    async def initialize_database(self):
        """
        Initialize database connection and ensure schema exists.
        """
        try:
            self.db_conn = psycopg2.connect(self.db_conn_string)
            self.db_conn.autocommit = False  # Use transactions

            # Test connection
            with self.db_conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            logger.info("Connected to PostgreSQL database")

        except Exception as e:
            logger.error("Failed to connect to database", error=str(e))
            raise

    def initialize_kafka_consumer(self):
        """
        Initialize Kafka consumer.
        """
        try:
            kafka_config = {
                'bootstrap.servers': self.config['kafka_brokers'],
                'group.id': self.consumer_group,
                'auto.offset.reset': 'earliest',  # Start from beginning if no offset
                'enable.auto.commit': False,  # Manual commit for exactly-once processing
                'session.timeout.ms': 30000,
                'heartbeat.interval.ms': 3000,
                'max.poll.interval.ms': 300000,
                'fetch.min.bytes': 1024,
                'fetch.max.bytes': 52428800,  # 50MB
                'fetch.max.wait.ms': 500,
            }

            self.consumer = Consumer(kafka_config)

            # Subscribe to topics
            self.consumer.subscribe(self.topics)

            logger.info(
                "Connected to Kafka",
                brokers=self.config['kafka_brokers'],
                group_id=self.consumer_group,
                topics=self.topics
            )

        except Exception as e:
            logger.error("Failed to initialize Kafka consumer", error=str(e))
            raise

    def validate_event(self, event_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate event data using Pydantic schemas.

        Args:
            event_data: Raw event data from Kafka

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Create envelope from raw data
            envelope = EventEnvelope(**event_data)

            # Validate the event based on its type
            event = envelope.event

            # Additional business rule validations
            if hasattr(event, 'timestamp'):
                # Check timestamp is not in future (allow 1 minute clock skew)
                max_future = datetime.utcnow() + timedelta(minutes=1)
                if event.timestamp > max_future:
                    return False, f"Event timestamp is in the future: {event.timestamp}"

            if hasattr(event, 'total_amount') and event.total_amount < 0:
                return False, f"Total amount cannot be negative: {event.total_amount}"

            if hasattr(event, 'price') and event.price < 0:
                return False, f"Price cannot be negative: {event.price}"

            if hasattr(event, 'quantity') and event.quantity <= 0:
                return False, f"Quantity must be positive: {event.quantity}"

            return True, None

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def store_event(self, cursor, event_data: Dict[str, Any]) -> bool:
        """
        Store a validated event in the database.

        Args:
            cursor: Database cursor
            event_data: Validated event data

        Returns:
            True if stored successfully
        """
        try:
            # Extract envelope data
            envelope = EventEnvelope(**event_data)
            event = envelope.event

            # Insert into raw.events table
            cursor.execute("""
                INSERT INTO raw.events (
                    event_id, event_type, timestamp, user_id, session_id,
                    product_id, category, price, quantity, order_id,
                    total_amount, currency, status, metadata, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (event_id) DO NOTHING
            """, (
                str(event.event_id),
                event.event_type,
                event.timestamp,
                getattr(event, 'user_id', None),
                getattr(event, 'session_id', None),
                getattr(event, 'product_id', None),
                getattr(event, 'category', None),
                getattr(event, 'price', None),
                getattr(event, 'quantity', None),
                getattr(event, 'order_id', None),
                getattr(event, 'total_amount', None),
                getattr(event, 'currency', 'USD'),
                getattr(event, 'status', None),
                json.dumps(getattr(event, 'metadata', {}))
            ))

            # Mark as processed (idempotent)
            cursor.execute("""
                INSERT INTO staging.processed_events (
                    event_id, processed_at, processor_version, batch_id
                ) VALUES (%s, NOW(), %s, %s)
                ON CONFLICT (event_id) DO NOTHING
            """, (
                str(event.event_id),
                "1.0",
                f"batch_{int(time.time())}"
            ))

            return True

        except Exception as e:
            logger.error(
                "Failed to store event",
                event_id=getattr(event, 'event_id', 'unknown'),
                error=str(e)
            )
            return False

    def store_invalid_event(
        self,
        cursor,
        raw_message: str,
        error_message: str,
        error_type: str = "validation_error"
    ):
        """
        Store invalid event in dead letter queue.

        Args:
            cursor: Database cursor
            raw_message: Raw Kafka message
            error_message: Validation error message
            error_type: Type of error
        """
        try:
            cursor.execute("""
                INSERT INTO raw.dead_letter (
                    event_id, raw_payload, error_reason, error_type, created_at
                ) VALUES (
                    COALESCE((%s::jsonb)->>'event_id', gen_random_uuid()::text),
                    %s, %s, %s, NOW()
                )
            """, (
                raw_message,
                raw_message,
                error_message,
                error_type
            ))

        except Exception as e:
            logger.error("Failed to store invalid event in dead letter queue", error=str(e))

    def store_metrics(self, cursor, batch_metrics: Dict[str, Any]):
        """
        Store consumer metrics.

        Args:
            cursor: Database cursor
            batch_metrics: Metrics for the current batch
        """
        try:
            cursor.execute("""
                INSERT INTO metrics.consumer_metrics (
                    timestamp, events_processed, events_failed, batch_size,
                    processing_time_ms, lag_messages
                ) VALUES (
                    NOW(), %s, %s, %s, %s, %s
                )
            """, (
                batch_metrics['events_processed'],
                batch_metrics['events_failed'],
                batch_metrics['batch_size'],
                batch_metrics['processing_time_ms'],
                batch_metrics.get('lag_messages', 0)
            ))

        except Exception as e:
            logger.error("Failed to store consumer metrics", error=str(e))

    def process_batch(self, messages: List[Dict[str, Any]]) -> ProcessingResult:
        """
        Process a batch of messages.

        Args:
            messages: List of message dictionaries from Kafka

        Returns:
            ProcessingResult with batch statistics
        """
        batch_start = time.time()
        processed = 0
        failed = 0

        try:
            with self.db_conn.cursor() as cursor:
                for message in messages:
                    try:
                        raw_payload = message['raw_payload']
                        event_data = json.loads(raw_payload)

                        # Validate event
                        is_valid, error_msg = self.validate_event(event_data)

                        if is_valid:
                            # Store valid event
                            if self.store_event(cursor, event_data):
                                processed += 1
                            else:
                                failed += 1
                                self.store_invalid_event(
                                    cursor, raw_payload, "Database storage failed", "storage_error"
                                )
                        else:
                            # Store invalid event
                            failed += 1
                            self.store_invalid_event(
                                cursor, raw_payload, error_msg, "validation_error"
                            )

                    except json.JSONDecodeError as e:
                        failed += 1
                        self.store_invalid_event(
                            cursor, message['raw_payload'], f"JSON decode error: {str(e)}", "parse_error"
                        )
                    except Exception as e:
                        failed += 1
                        self.store_invalid_event(
                            cursor, message['raw_payload'], f"Processing error: {str(e)}", "processing_error"
                        )

                # Store batch metrics
                batch_metrics = {
                    'events_processed': processed,
                    'events_failed': failed,
                    'batch_size': len(messages),
                    'processing_time_ms': int((time.time() - batch_start) * 1000),
                }
                self.store_metrics(cursor, batch_metrics)

                # Commit transaction
                self.db_conn.commit()

        except Exception as e:
            logger.error("Batch processing failed, rolling back", error=str(e))
            if self.db_conn:
                self.db_conn.rollback()
            return ProcessingResult(
                event_id=UUID('00000000-0000-0000-0000-000000000000'),  # Dummy ID for batch
                success=False,
                error_message=f"Batch processing failed: {str(e)}",
                processing_time_ms=int((time.time() - batch_start) * 1000)
            )

        # Update global counters
        self.events_processed += processed
        self.events_failed += failed
        self.batches_processed += 1

        processing_time = int((time.time() - batch_start) * 1000)

        logger.info(
            "Batch processed",
            batch_size=len(messages),
            processed=processed,
            failed=failed,
            processing_time_ms=processing_time
        )

        return ProcessingResult(
            event_id=UUID('00000000-0000-0000-0000-000000000000'),  # Dummy ID for batch
            success=True,
            processing_time_ms=processing_time
        )

    async def consume_events(self):
        """
        Main consumption loop.
        """
        logger.info("Starting event consumption")

        batch = []
        batch_start = time.time()

        try:
            while True:
                # Poll for messages
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    # No message available, check if batch should be processed
                    if batch and (time.time() - batch_start) >= 1.0:  # Process batch every second
                        self.process_batch(batch)
                        batch = []
                        batch_start = time.time()
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition, continue
                        continue
                    else:
                        logger.error("Kafka consumer error", error=str(msg.error()))
                        continue

                # Add message to batch
                message_data = {
                    'topic': msg.topic(),
                    'partition': msg.partition(),
                    'offset': msg.offset(),
                    'key': msg.key().decode('utf-8') if msg.key() else None,
                    'raw_payload': msg.value().decode('utf-8'),
                    'timestamp': msg.timestamp()[1] if msg.timestamp() else None,
                }

                batch.append(message_data)

                # Process batch if it reaches target size
                if len(batch) >= self.batch_size:
                    self.process_batch(batch)
                    batch = []
                    batch_start = time.time()

                    # Manual commit offsets
                    self.consumer.commit()

                # Log progress every 1000 events
                total_events = self.events_processed + self.events_failed
                if total_events % 1000 == 0 and total_events > 0:
                    elapsed = time.time() - self.start_time
                    throughput = total_events / elapsed

                    logger.info(
                        "Consumer progress",
                        total_events=total_events,
                        processed=self.events_processed,
                        failed=self.events_failed,
                        batches=self.batches_processed,
                        throughput_events_sec=f"{throughput:.1f}",
                        success_rate=f"{(self.events_processed/total_events)*100:.1f}%"
                    )

        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
        except Exception as e:
            logger.error("Error in consumption loop", error=str(e))
            raise
        finally:
            # Process final batch
            if batch:
                self.process_batch(batch)

            # Final commit
            if self.consumer:
                self.consumer.commit()
                self.consumer.close()

            # Final stats
            total_time = time.time() - self.start_time
            total_events = self.events_processed + self.events_failed
            avg_throughput = total_events / total_time if total_time > 0 else 0

            logger.info(
                "Consumer stopped",
                total_events=total_events,
                processed=self.events_processed,
                failed=self.events_failed,
                batches=self.batches_processed,
                total_time=f"{total_time:.1f}s",
                avg_throughput=f"{avg_throughput:.1f} events/sec"
            )

    async def run(self):
        """
        Run the event consumer.
        """
        await self.initialize_database()
        self.initialize_kafka_consumer()
        await self.consume_events()


async def main():
    """
    Main entry point for the event consumer service.
    """
    # Setup logging
    setup_logging("consumer", level="INFO")

    # Load and validate configuration
    config = load_config()
    validate_config(config)

    logger.info("Starting Event Consumer Service", config=config)

    # Create and run consumer
    consumer = EventConsumer(config)

    try:
        await consumer.run()
    except Exception as e:
        logger.error("Event consumer failed", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())