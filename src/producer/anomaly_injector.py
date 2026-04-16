"""
Anomaly injector for the event producer.

This module provides functionality to inject realistic anomalies into the event stream
for testing anomaly detection capabilities.
"""

import random
from decimal import Decimal
from typing import Dict, Any, Optional

from ..shared import get_logger

logger = get_logger(__name__)


class AnomalyInjector:
    """
    Injects anomalies into event streams for testing purposes.

    Supports various types of anomalies:
    - Fraudulent purchases (inflated revenue)
    - Bot traffic (bursts of page views)
    - Data quality issues (missing fields)
    """

    def __init__(self, anomaly_rate: float = 0.005):
        """
        Initialize the anomaly injector.

        Args:
            anomaly_rate: Probability of injecting an anomaly (0.0 to 1.0)
        """
        self.anomaly_rate = anomaly_rate
        self.anomaly_count = 0
        self.total_events = 0

    def should_inject_anomaly(self) -> bool:
        """
        Determine if an anomaly should be injected based on the configured rate.

        Returns:
            True if anomaly should be injected
        """
        return random.random() < self.anomaly_rate

    def inject_purchase_fraud(
        self,
        event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Inject fraudulent purchase anomaly by inflating revenue.

        Args:
            event_data: Original purchase event data

        Returns:
            Modified event data with inflated revenue
        """
        # Inflate revenue by 5-20x
        multiplier = random.uniform(5.0, 20.0)
        original_revenue = Decimal(str(event_data.get('total_amount', 0)))
        event_data['total_amount'] = float(original_revenue * Decimal(str(multiplier)))

        # Add suspicious metadata
        event_data['metadata'] = event_data.get('metadata', {})
        event_data['metadata']['anomaly_type'] = 'fraudulent_purchase'
        event_data['metadata']['revenue_multiplier'] = multiplier

        logger.warning(
            "Injected fraudulent purchase anomaly",
            event_id=event_data.get('event_id'),
            original_revenue=float(original_revenue),
            inflated_revenue=event_data['total_amount']
        )

        return event_data

    def inject_bot_traffic_burst(
        self,
        event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Inject bot traffic anomaly by creating rapid page view bursts.

        Note: This method modifies the event timing to create bursts.
        The actual burst generation is handled by the producer.

        Args:
            event_data: Original page view event data

        Returns:
            Modified event data marked for burst
        """
        # Mark event for burst generation
        event_data['metadata'] = event_data.get('metadata', {})
        event_data['metadata']['anomaly_type'] = 'bot_traffic_burst'
        event_data['metadata']['burst_size'] = random.randint(20, 100)

        logger.warning(
            "Marked event for bot traffic burst",
            event_id=event_data.get('event_id'),
            burst_size=event_data['metadata']['burst_size']
        )

        return event_data

    def inject_data_quality_issue(
        self,
        event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Inject data quality anomaly by corrupting or removing fields.

        Args:
            event_data: Original event data

        Returns:
            Modified event data with quality issues
        """
        corruption_types = ['missing_user_id', 'invalid_price', 'corrupt_metadata']

        corruption_type = random.choice(corruption_types)

        if corruption_type == 'missing_user_id':
            event_data['user_id'] = None
        elif corruption_type == 'invalid_price':
            if 'price' in event_data:
                event_data['price'] = -999.99
            elif 'total_amount' in event_data:
                event_data['total_amount'] = -999.99
        elif corruption_type == 'corrupt_metadata':
            event_data['metadata'] = {"corrupted": True, "error": "data_quality_issue"}

        event_data['metadata'] = event_data.get('metadata', {})
        event_data['metadata']['anomaly_type'] = 'data_quality_issue'
        event_data['metadata']['corruption_type'] = corruption_type

        logger.warning(
            "Injected data quality anomaly",
            event_id=event_data.get('event_id'),
            corruption_type=corruption_type
        )

        return event_data

    def inject_anomaly(
        self,
        event_data: Dict[str, Any],
        event_type: str
    ) -> Dict[str, Any]:
        """
        Inject an appropriate anomaly based on event type.

        Args:
            event_data: Original event data
            event_type: Type of event ('page_view', 'cart_event', 'purchase')

        Returns:
            Modified event data with injected anomaly
        """
        self.total_events += 1

        if not self.should_inject_anomaly():
            return event_data

        self.anomaly_count += 1

        # Choose anomaly type based on event type
        if event_type == 'purchase':
            # 70% fraud, 30% data quality
            if random.random() < 0.7:
                return self.inject_purchase_fraud(event_data)
            else:
                return self.inject_data_quality_issue(event_data)

        elif event_type == 'page_view':
            # 60% bot traffic, 40% data quality
            if random.random() < 0.6:
                return self.inject_bot_traffic_burst(event_data)
            else:
                return self.inject_data_quality_issue(event_data)

        elif event_type == 'cart_event':
            # Mostly data quality issues for cart events
            return self.inject_data_quality_issue(event_data)

        else:
            # Default to data quality issue
            return self.inject_data_quality_issue(event_data)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get anomaly injection statistics.

        Returns:
            Dictionary with injection statistics
        """
        anomaly_rate = self.anomaly_count / max(self.total_events, 1)

        return {
            'total_events': self.total_events,
            'anomalies_injected': self.anomaly_count,
            'anomaly_rate': anomaly_rate,
            'configured_rate': self.anomaly_rate,
        }