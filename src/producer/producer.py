"""
Event Producer Service.

Generates realistic e-commerce events and publishes them to Kafka/Redpanda
at configurable throughput rates with anomaly injection capabilities.
"""

import asyncio
import random
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from uuid import uuid4

from faker import Faker

from ..shared import (
    setup_logging,
    get_logger,
    load_config,
    validate_config,
    PageViewEvent,
    CartEvent,
    PurchaseEvent,
    EventEnvelope,
)
from .anomaly_injector import AnomalyInjector

logger = get_logger(__name__)


class EventProducer:
    """
    High-throughput event producer for e-commerce analytics.

    Generates realistic events across multiple types:
    - Page views (browsing behavior)
    - Cart events (add/remove items)
    - Purchases (completed transactions)

    Supports anomaly injection for testing detection capabilities.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the event producer.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.faker = Faker()

        # Throughput configuration
        self.target_throughput = config['producer_throughput']  # events per second
        self.anomaly_injector = AnomalyInjector(config['producer_anomaly_rate'])

        # Event type distributions (percentages)
        self.event_distributions = {
            'page_view': 0.4,    # 40% page views
            'cart_event': 0.3,   # 30% cart events
            'purchase': 0.3,     # 30% purchases
        }

        # Counters
        self.events_sent = 0
        self.start_time = time.time()

        # Kafka producer (will be initialized)
        self.producer = None

        logger.info(
            "Initialized event producer",
            target_throughput=self.target_throughput,
            anomaly_rate=config['producer_anomaly_rate']
        )

    async def initialize_kafka(self):
        """
        Initialize Kafka producer connection.
        """
        try:
            from confluent_kafka import Producer

            # Kafka configuration
            kafka_config = {
                'bootstrap.servers': self.config['kafka_brokers'],
                'client.id': 'ecommerce-producer',
                'acks': '1',  # Wait for leader acknowledgment
                'retries': 3,
                'retry.backoff.ms': 100,
                'delivery.timeout.ms': 30000,
            }

            self.producer = Producer(kafka_config)

            # Test connection
            metadata = self.producer.list_topics(timeout=10)
            available_topics = list(metadata.topics.keys())

            logger.info(
                "Connected to Kafka",
                brokers=self.config['kafka_brokers'],
                available_topics=available_topics
            )

        except Exception as e:
            logger.error("Failed to initialize Kafka producer", error=str(e))
            raise

    def generate_user_session(self) -> Dict[str, Any]:
        """
        Generate a user session context.

        Returns:
            Dictionary with user and session information
        """
        user_id = f"user_{random.randint(1, 100000)}"
        session_id = str(uuid4())

        return {
            'user_id': user_id,
            'session_id': session_id,
            'country': self.faker.country_code(),
            'user_agent': self.faker.user_agent(),
            'ip_address': self.faker.ipv4(),
        }

    def generate_page_view_event(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a page view event.

        Args:
            session: User session context

        Returns:
            Page view event data
        """
        categories = ['electronics', 'clothing', 'books', 'home', 'sports', 'beauty']
        products = {
            'electronics': ['laptop', 'phone', 'tablet', 'headphones', 'camera'],
            'clothing': ['shirt', 'pants', 'dress', 'shoes', 'jacket'],
            'books': ['novel', 'textbook', 'biography', 'cookbook', 'mystery'],
            'home': ['chair', 'table', 'lamp', 'bedding', 'kitchenware'],
            'sports': ['ball', 'racket', 'shoes', 'equipment', 'apparel'],
            'beauty': ['makeup', 'skincare', 'haircare', 'fragrance', 'tools'],
        }

        category = random.choice(categories)
        product = random.choice(products[category])

        event_data = {
            'event_id': str(uuid4()),
            'event_type': 'page_view',
            'timestamp': datetime.utcnow().isoformat(),
            'user_id': session['user_id'],
            'session_id': session['session_id'],
            'product_id': f"{category}_{product}_{random.randint(1, 1000)}",
            'category': category,
            'url': f"/products/{category}/{product}",
            'referrer': random.choice([
                None, 'google.com', 'facebook.com', 'instagram.com',
                f"/products/{random.choice(categories)}"
            ]),
            'user_agent': session['user_agent'],
            'ip_address': session['ip_address'],
            'campaign_id': random.choice([None, f"campaign_{random.randint(1, 10)}"]),
        }

        return event_data

    def generate_cart_event(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a cart event (add or remove).

        Args:
            session: User session context

        Returns:
            Cart event data
        """
        categories = ['electronics', 'clothing', 'books', 'home', 'sports']
        products = {
            'electronics': ['laptop', 'phone', 'tablet', 'headphones'],
            'clothing': ['shirt', 'pants', 'dress', 'shoes'],
            'books': ['novel', 'textbook', 'biography'],
            'home': ['chair', 'table', 'lamp'],
            'sports': ['ball', 'racket', 'shoes'],
        }

        category = random.choice(categories)
        product = random.choice(products[category])
        action = random.choice(['add', 'remove'])

        # Higher probability of adding items
        if action == 'remove':
            action = 'add' if random.random() < 0.7 else 'remove'

        event_data = {
            'event_id': str(uuid4()),
            'event_type': 'cart_event',
            'timestamp': datetime.utcnow().isoformat(),
            'user_id': session['user_id'],
            'session_id': session['session_id'],
            'product_id': f"{category}_{product}_{random.randint(1, 1000)}",
            'category': category,
            'quantity': random.randint(1, 5),
            'price': round(random.uniform(10, 500), 2),
            'currency': 'USD',
            'action': action,
        }

        return event_data

    def generate_purchase_event(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a purchase event.

        Args:
            session: User session context

        Returns:
            Purchase event data
        """
        # Generate 1-5 items in the order
        num_items = random.randint(1, 5)
        items = []

        categories = ['electronics', 'clothing', 'books', 'home', 'sports', 'beauty']
        products = {
            'electronics': ['laptop', 'phone', 'tablet', 'headphones', 'camera'],
            'clothing': ['shirt', 'pants', 'dress', 'shoes', 'jacket'],
            'books': ['novel', 'textbook', 'biography', 'cookbook'],
            'home': ['chair', 'table', 'lamp', 'bedding'],
            'sports': ['ball', 'racket', 'shoes', 'equipment'],
            'beauty': ['makeup', 'skincare', 'haircare', 'fragrance'],
        }

        total_amount = 0
        for _ in range(num_items):
            category = random.choice(categories)
            product = random.choice(products[category])
            quantity = random.randint(1, 3)
            price = round(random.uniform(15, 800), 2)
            item_total = quantity * price
            total_amount += item_total

            items.append({
                'product_id': f"{category}_{product}_{random.randint(1, 1000)}",
                'category': category,
                'quantity': quantity,
                'price': price,
                'total': item_total,
            })

        # Add shipping and tax
        shipping_cost = round(random.uniform(0, 25), 2)
        tax_amount = round(total_amount * 0.08, 2)  # 8% tax
        total_amount += shipping_cost + tax_amount

        event_data = {
            'event_id': str(uuid4()),
            'event_type': 'purchase',
            'timestamp': datetime.utcnow().isoformat(),
            'user_id': session['user_id'],
            'session_id': session['session_id'],
            'order_id': f"order_{random.randint(100000, 999999)}",
            'items': items,
            'total_amount': round(total_amount, 2),
            'currency': 'USD',
            'payment_method': random.choice(['credit_card', 'paypal', 'apple_pay', 'google_pay']),
            'shipping_address': {
                'street': self.faker.street_address(),
                'city': self.faker.city(),
                'state': self.faker.state_abbr(),
                'zip_code': self.faker.zipcode(),
                'country': session['country'],
            },
            'billing_address': {
                'street': self.faker.street_address(),
                'city': self.faker.city(),
                'state': self.faker.state_abbr(),
                'zip_code': self.faker.zipcode(),
                'country': session['country'],
            },
            'discount_code': random.choice([None, f"SAVE{random.randint(10, 50)}"]),
            'discount_amount': round(random.uniform(0, 50), 2) if random.random() < 0.3 else 0,
            'tax_amount': tax_amount,
            'shipping_cost': shipping_cost,
            'status': 'completed',
        }

        return event_data

    def generate_event(self) -> Dict[str, Any]:
        """
        Generate a random event based on configured distributions.

        Returns:
            Event data dictionary
        """
        # Select event type based on distribution
        rand = random.random()
        cumulative = 0

        for event_type, probability in self.event_distributions.items():
            cumulative += probability
            if rand <= cumulative:
                break

        # Generate user session
        session = self.generate_user_session()

        # Generate event based on type
        if event_type == 'page_view':
            event_data = self.generate_page_view_event(session)
        elif event_type == 'cart_event':
            event_data = self.generate_cart_event(session)
        elif event_type == 'purchase':
            event_data = self.generate_purchase_event(session)
        else:
            # Fallback to page view
            event_data = self.generate_page_view_event(session)

        # Inject anomaly if configured
        event_data = self.anomaly_injector.inject_anomaly(event_data, event_type)

        return event_data

    def publish_to_kafka(self, event_data: Dict[str, Any]) -> bool:
        """
        Publish event to Kafka topic.

        Args:
            event_data: Event data to publish

        Returns:
            True if successful, False otherwise
        """
        try:
            # Determine topic based on event type
            event_type = event_data['event_type']
            if event_type == 'page_view':
                topic = 'page_views'
            elif event_type == 'cart_event':
                topic = 'cart_events'
            elif event_type == 'purchase':
                topic = 'purchases'
            else:
                topic = 'events'  # fallback topic

            # Create envelope
            envelope = EventEnvelope(
                event=event_data,  # This will be validated by Pydantic
                source='producer',
                version='1.0'
            )

            # Serialize to JSON
            message_value = envelope.json()

            # Publish to Kafka
            self.producer.produce(
                topic=topic,
                value=message_value,
                key=event_data.get('user_id', '').encode('utf-8'),
                callback=self._delivery_callback
            )

            # Poll to handle delivery reports
            self.producer.poll(0)

            return True

        except Exception as e:
            logger.error(
                "Failed to publish event to Kafka",
                error=str(e),
                event_id=event_data.get('event_id'),
                event_type=event_data.get('event_type')
            )
            return False

    def _delivery_callback(self, err, msg):
        """
        Kafka delivery callback.

        Args:
            err: Error if delivery failed
            msg: Message metadata if successful
        """
        if err:
            logger.error(
                "Message delivery failed",
                error=str(err),
                topic=msg.topic() if msg else None,
                partition=msg.partition() if msg else None
            )
        else:
            logger.debug(
                "Message delivered successfully",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def produce_events(self, duration_seconds: Optional[int] = None):
        """
        Main event production loop.

        Args:
            duration_seconds: How long to run (None = indefinite)
        """
        logger.info("Starting event production", target_throughput=self.target_throughput)

        start_time = time.time()
        last_log_time = start_time
        events_in_interval = 0

        try:
            while True:
                # Check if duration limit reached
                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    break

                # Generate and publish event
                event_data = self.generate_event()
                success = self.publish_to_kafka(event_data)

                if success:
                    self.events_sent += 1
                    events_in_interval += 1

                # Rate limiting to achieve target throughput
                target_interval = 1.0 / self.target_throughput
                await asyncio.sleep(target_interval * random.uniform(0.8, 1.2))  # Add jitter

                # Log progress every 10 seconds
                current_time = time.time()
                if current_time - last_log_time >= 10:
                    elapsed = current_time - last_log_time
                    actual_throughput = events_in_interval / elapsed

                    anomaly_stats = self.anomaly_injector.get_stats()

                    logger.info(
                        "Production stats",
                        total_events=self.events_sent,
                        throughput=f"{actual_throughput:.1f} events/sec",
                        anomaly_rate=f"{anomaly_stats['anomaly_rate']:.4f}",
                        anomalies_injected=anomaly_stats['anomalies_injected']
                    )

                    events_in_interval = 0
                    last_log_time = current_time

        except KeyboardInterrupt:
            logger.info("Event production interrupted by user")
        except Exception as e:
            logger.error("Error in event production loop", error=str(e))
            raise
        finally:
            # Flush any remaining messages
            if self.producer:
                self.producer.flush(timeout=10)
                logger.info("Kafka producer flushed")

            # Final stats
            total_time = time.time() - start_time
            final_throughput = self.events_sent / total_time if total_time > 0 else 0
            anomaly_stats = self.anomaly_injector.get_stats()

            logger.info(
                "Event production completed",
                total_events=self.events_sent,
                total_time=f"{total_time:.1f}s",
                avg_throughput=f"{final_throughput:.1f} events/sec",
                final_anomaly_rate=f"{anomaly_stats['anomaly_rate']:.4f}"
            )

    async def run(self):
        """
        Run the event producer.
        """
        await self.initialize_kafka()
        await self.produce_events()


async def main():
    """
    Main entry point for the event producer service.
    """
    # Setup logging
    setup_logging("producer", level="INFO")

    # Load and validate configuration
    config = load_config()
    validate_config(config)

    logger.info("Starting Event Producer Service", config=config)

    # Create and run producer
    producer = EventProducer(config)

    try:
        await producer.run()
    except Exception as e:
        logger.error("Event producer failed", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())