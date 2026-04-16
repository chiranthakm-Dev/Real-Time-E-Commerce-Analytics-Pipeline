"""
Shared utilities for the Real-Time E-Commerce Analytics Pipeline.

This module provides common functionality used across all services:
- Structured logging configuration
- Configuration management
- Common helper functions
- Metrics utilities
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from python_dotenv import load_dotenv


def setup_logging(
    service_name: str,
    level: str = "INFO",
    log_to_file: bool = True,
    log_dir: str = "logs"
) -> None:
    """
    Configure structured logging for the service.

    Args:
        service_name: Name of the service (e.g., 'producer', 'consumer')
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_to_file: Whether to log to file in addition to console
        log_dir: Directory for log files
    """
    # Load environment variables
    load_dotenv()

    # Create logs directory if it doesn't exist
    if log_to_file:
        Path(log_dir).mkdir(exist_ok=True)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level)
        ),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level))

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(console_handler)

    # File handler (if enabled)
    if log_to_file:
        file_handler = logging.FileHandler(
            f"{log_dir}/{service_name}.log",
            encoding='utf-8'
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )
        logger.addHandler(file_handler)

    # Set up structlog logger
    structlog.get_logger(service_name)


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """
    Get a structured logger for the given name.

    Args:
        name: Logger name

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


def load_config() -> Dict[str, Any]:
    """
    Load configuration from environment variables.

    Returns:
        Dictionary containing all configuration values
    """
    load_dotenv()

    config = {
        # PostgreSQL Configuration
        "postgres_host": os.getenv("POSTGRES_HOST", "postgres"),
        "postgres_port": int(os.getenv("POSTGRES_PORT", "5432")),
        "postgres_db": os.getenv("POSTGRES_DB", "analytics"),
        "postgres_user": os.getenv("POSTGRES_USER", "postgres"),
        "postgres_password": os.getenv("POSTGRES_PASSWORD", "postgres_password_here"),

        # Kafka/Redpanda Configuration
        "kafka_brokers": os.getenv("KAFKA_BROKERS", "redpanda:9092"),
        "consumer_group_id": os.getenv("CONSUMER_GROUP_ID", "ecommerce-consumer-group"),
        "consumer_batch_size": int(os.getenv("CONSUMER_BATCH_SIZE", "500")),

        # Producer Configuration
        "producer_throughput": int(os.getenv("PRODUCER_THROUGHPUT", "500")),
        "producer_anomaly_rate": float(os.getenv("PRODUCER_ANOMALY_RATE", "0.005")),

        # Anomaly Detection Configuration
        "anomaly_contamination": float(os.getenv("ANOMALY_CONTAMINATION", "0.01")),
        "anomaly_polling_interval": int(os.getenv("ANOMALY_POLLING_INTERVAL", "60")),
        "anomaly_window_size": int(os.getenv("ANOMALY_WINDOW_SIZE", "500")),
        "anomaly_metrics_port": int(os.getenv("ANOMALY_METRICS_PORT", "8000")),

        # Grafana Configuration
        "grafana_admin_user": os.getenv("GF_SECURITY_ADMIN_USER", "admin"),
        "grafana_admin_password": os.getenv("GF_SECURITY_ADMIN_PASSWORD", "admin"),

        # Slack Alerting
        "slack_webhook_url": os.getenv("SLACK_WEBHOOK_URL"),

        # Prometheus Configuration
        "prometheus_port": int(os.getenv("PROMETHEUS_PORT", "9090")),

        # dbt Configuration
        "dbt_profiles_dir": os.getenv("DBT_PROFILES_DIR", "./dbt"),
        "dbt_project_dir": os.getenv("DBT_PROJECT_DIR", "./dbt"),

        # Docker Configuration
        "compose_project_name": os.getenv("COMPOSE_PROJECT_NAME", "ecommerce-analytics"),
    }

    return config


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration values.

    Args:
        config: Configuration dictionary

    Raises:
        ValueError: If configuration is invalid
    """
    required_fields = [
        "postgres_password",
        "kafka_brokers",
    ]

    missing_fields = [
        field for field in required_fields
        if not config.get(field)
    ]

    if missing_fields:
        raise ValueError(f"Missing required configuration fields: {missing_fields}")

    # Validate numeric ranges
    if config["producer_throughput"] <= 0:
        raise ValueError("producer_throughput must be positive")

    if not (0 <= config["producer_anomaly_rate"] <= 1):
        raise ValueError("producer_anomaly_rate must be between 0 and 1")

    if not (0 <= config["anomaly_contamination"] <= 1):
        raise ValueError("anomaly_contamination must be between 0 and 1")


def create_postgres_connection_string(config: Dict[str, Any]) -> str:
    """
    Create PostgreSQL connection string from config.

    Args:
        config: Configuration dictionary

    Returns:
        PostgreSQL connection string
    """
    return (
        f"postgresql://{config['postgres_user']}:"
        f"{config['postgres_password']}@"
        f"{config['postgres_host']}:"
        f"{config['postgres_port']}/"
        f"{config['postgres_db']}"
    )


def safe_json_dumps(obj: Any) -> str:
    """
    Safely serialize object to JSON string.

    Args:
        obj: Object to serialize

    Returns:
        JSON string representation
    """
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except Exception as e:
        return f"<serialization_error: {str(e)}>"


def get_project_root() -> Path:
    """
    Get the project root directory.

    Returns:
        Path to project root
    """
    return Path(__file__).parent.parent.parent


def ensure_directory(path: Path) -> None:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path
    """
    path.mkdir(parents=True, exist_ok=True)