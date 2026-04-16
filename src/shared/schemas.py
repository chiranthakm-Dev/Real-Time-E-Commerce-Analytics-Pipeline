"""
Shared schemas and data models for the Real-Time E-Commerce Analytics Pipeline.

This module contains Pydantic models that define the structure of events
flowing through the system. These schemas ensure data consistency and
provide validation across producer, consumer, and anomaly detection services.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator


class EventType(str, Enum):
    """Enumeration of all supported event types."""
    PAGE_VIEW = "page_view"
    CART_ADD = "cart_add"
    CART_REMOVE = "cart_remove"
    PURCHASE = "purchase"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    SEARCH = "search"
    PRODUCT_VIEW = "product_view"


class Currency(str, Enum):
    """Supported currencies."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"


class BaseEvent(BaseModel):
    """Base event model with common fields."""
    event_id: UUID = Field(default_factory=uuid4, description="Unique event identifier")
    event_type: EventType = Field(..., description="Type of the event")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp in UTC")
    user_id: Optional[str] = Field(None, description="User identifier (nullable for anonymous events)")
    session_id: Optional[str] = Field(None, description="Session identifier")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional event metadata")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
            Decimal: lambda v: float(v),
        }


class PageViewEvent(BaseEvent):
    """Page view event schema."""
    event_type: EventType = EventType.PAGE_VIEW
    product_id: Optional[str] = Field(None, description="Product being viewed")
    category: Optional[str] = Field(None, description="Product category")
    url: str = Field(..., description="Page URL")
    referrer: Optional[str] = Field(None, description="Referrer URL")
    user_agent: Optional[str] = Field(None, description="User agent string")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    campaign_id: Optional[str] = Field(None, description="Marketing campaign identifier")


class CartEvent(BaseEvent):
    """Cart event schema (add/remove items)."""
    product_id: str = Field(..., description="Product identifier")
    category: str = Field(..., description="Product category")
    quantity: int = Field(..., description="Quantity changed")
    price: Decimal = Field(..., description="Unit price")
    currency: Currency = Field(default=Currency.USD, description="Currency code")
    action: str = Field(..., description="Action: 'add' or 'remove'")

    @validator('action')
    def validate_action(cls, v):
        if v not in ['add', 'remove']:
            raise ValueError('action must be either "add" or "remove"')
        return v

    @validator('quantity')
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError('quantity must be positive')
        return v


class PurchaseEvent(BaseEvent):
    """Purchase event schema."""
    event_type: EventType = EventType.PURCHASE
    order_id: str = Field(..., description="Unique order identifier")
    items: List[Dict[str, Any]] = Field(..., description="List of purchased items")
    total_amount: Decimal = Field(..., description="Total order amount")
    currency: Currency = Field(default=Currency.USD, description="Currency code")
    payment_method: Optional[str] = Field(None, description="Payment method used")
    shipping_address: Optional[Dict[str, Any]] = Field(None, description="Shipping address")
    billing_address: Optional[Dict[str, Any]] = Field(None, description="Billing address")
    discount_code: Optional[str] = Field(None, description="Applied discount code")
    discount_amount: Optional[Decimal] = Field(None, description="Discount amount")
    tax_amount: Optional[Decimal] = Field(None, description="Tax amount")
    shipping_cost: Optional[Decimal] = Field(None, description="Shipping cost")
    status: str = Field(default="completed", description="Order status")


class UserEvent(BaseEvent):
    """User authentication event schema."""
    action: str = Field(..., description="Action: 'login' or 'logout'")

    @validator('action')
    def validate_action(cls, v):
        if v not in ['login', 'logout']:
            raise ValueError('action must be either "login" or "logout"')
        return v


class SearchEvent(BaseEvent):
    """Search event schema."""
    event_type: EventType = EventType.SEARCH
    query: str = Field(..., description="Search query string")
    results_count: Optional[int] = Field(None, description="Number of search results")
    filters: Optional[Dict[str, Any]] = Field(None, description="Applied search filters")


class ProductViewEvent(BaseEvent):
    """Product view event schema."""
    event_type: EventType = EventType.PRODUCT_VIEW
    product_id: str = Field(..., description="Product identifier")
    category: str = Field(..., description="Product category")
    price: Optional[Decimal] = Field(None, description="Product price")
    currency: Currency = Field(default=Currency.USD, description="Currency code")
    brand: Optional[str] = Field(None, description="Product brand")
    tags: Optional[List[str]] = Field(None, description="Product tags")


# Union type for all event types
Event = Union[
    PageViewEvent,
    CartEvent,
    PurchaseEvent,
    UserEvent,
    SearchEvent,
    ProductViewEvent,
]


class EventEnvelope(BaseModel):
    """Envelope for serializing events with additional context."""
    event: Event = Field(..., description="The event data")
    source: str = Field(..., description="Source system that generated the event")
    version: str = Field(default="1.0", description="Event schema version")
    ingested_at: datetime = Field(default_factory=datetime.utcnow, description="Ingestion timestamp")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
            Decimal: lambda v: float(v),
        }


class ProcessingResult(BaseModel):
    """Result of processing an event."""
    event_id: UUID = Field(..., description="Event identifier")
    success: bool = Field(..., description="Whether processing succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")
    batch_id: Optional[UUID] = Field(None, description="Batch identifier")


class AnomalyResult(BaseModel):
    """Result of anomaly detection."""
    event_id: UUID = Field(..., description="Event identifier")
    anomaly_score: float = Field(..., description="Anomaly score (0-1, higher = more anomalous)")
    anomaly_type: str = Field(..., description="Type of anomaly detected")
    threshold: float = Field(..., description="Detection threshold used")
    features: Dict[str, Any] = Field(..., description="Features used for detection")
    model_version: str = Field(..., description="Model version used")
    detected_at: datetime = Field(default_factory=datetime.utcnow, description="Detection timestamp")