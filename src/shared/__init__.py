"""
Shared utilities and schemas for the Real-Time E-Commerce Analytics Pipeline.

This package contains common code used across all services:
- Data schemas and models
- Logging and configuration utilities
- Common helper functions
"""

from .schemas import (
    BaseEvent,
    Event,
    EventEnvelope,
    EventType,
    PageViewEvent,
    CartEvent,
    PurchaseEvent,
    UserEvent,
    SearchEvent,
    ProductViewEvent,
    ProcessingResult,
    AnomalyResult,
    Currency,
)
from .utils import (
    setup_logging,
    get_logger,
    load_config,
    validate_config,
    create_postgres_connection_string,
    safe_json_dumps,
    get_project_root,
    ensure_directory,
)

__all__ = [
    # Schemas
    "BaseEvent",
    "Event",
    "EventEnvelope",
    "EventType",
    "PageViewEvent",
    "CartEvent",
    "PurchaseEvent",
    "UserEvent",
    "SearchEvent",
    "ProductViewEvent",
    "ProcessingResult",
    "AnomalyResult",
    "Currency",

    # Utils
    "setup_logging",
    "get_logger",
    "load_config",
    "validate_config",
    "create_postgres_connection_string",
    "safe_json_dumps",
    "get_project_root",
    "ensure_directory",
]