"""IA Brasil — Custom JSON Encoder.

Custom JSON encoder to handle non-serializable objects commonly found in the application.
This includes database model instances, enum values, date/datetime objects, and other types
that are not natively serializable by json.dumps.

Usage:
    from src.core.json_encoder import CustomJSONEncoder
    json.dumps(data, cls=CustomJSONEncoder, ensure_ascii=False, indent=2)
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.orm import DeclarativeBase


class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles common non-serializable types.

    Handles:
    - Enum values (converts to their value)
    - date/datetime/time objects (converts to ISO format strings)
    - Decimal objects (converts to float)
    - UUID objects (converts to string)
    - SQLAlchemy model instances (converts to dict of their attributes)
    - Other objects with __dict__ attribute
    """

    def default(self, obj: Any) -> Any:
        """Override default method to handle non-serializable objects.

        Args:
            obj: The object to serialize

        Returns:
            Serializable representation of the object

        Raises:
            TypeError: If the object cannot be serialized

        Note:
            This method intentionally has multiple return statements (one per type)
            to provide clear, type-specific serialization logic. This is more
            maintainable than a single complex return statement.
        """
        # Handle basic types that are already JSON-serializable
        # These should not be processed by our custom logic
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj

        # Handle Enum values
        if isinstance(obj, Enum):
            return obj.value

        # Handle date/datetime/time objects
        if isinstance(obj, (date, datetime, time)):
            return obj.isoformat()

        # Handle Decimal and UUID objects
        if isinstance(obj, (Decimal, UUID)):
            return float(obj) if isinstance(obj, Decimal) else str(obj)

        # Handle SQLAlchemy model instances - use explicit type check
        # Check if it's a DeclarativeBase instance but not a basic type
        basic_types = (Decimal, UUID, Enum, date, datetime, time)
        if isinstance(obj, DeclarativeBase) and not isinstance(obj, basic_types):
            return self._serialize_sqlalchemy_model(obj)

        # Handle dictionaries
        if isinstance(obj, dict):
            return self._serialize_dict(obj)

        # Handle lists
        if isinstance(obj, list):
            return self._serialize_list(obj)

        # Handle other objects with __dict__ attribute
        if hasattr(obj, "__dict__"):
            return self._serialize_object_with_dict(obj)

        return super().default(obj)

    def _serialize_sqlalchemy_model(self, model: DeclarativeBase) -> dict[str, Any]:
        """Serialize a SQLAlchemy model instance to a dictionary.

        Args:
            model: SQLAlchemy model instance

        Returns:
            Dictionary representation of the model
        """
        result = {}

        # Get all attributes from the model
        for key, value in model.__dict__.items():
            # Skip private attributes and SQLAlchemy internal attributes
            if key.startswith("_"):
                continue

            # Recursively serialize nested objects
            try:
                result[key] = self.default(value)
            except TypeError:
                # If we can't serialize it, skip it or convert to string
                result[key] = str(value)

        return result

    def _serialize_dict(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Serialize a dictionary with potential nested complex objects.

        Args:
            obj: Dictionary to serialize

        Returns:
            Dictionary with all values serialized
        """
        result = {}
        for key, value in obj.items():
            try:
                result[key] = self.default(value)
            except TypeError:
                # If we can't serialize it, skip it or convert to string
                result[key] = str(value)
        return result

    def _serialize_list(self, obj: list[Any]) -> list[Any]:
        """Serialize a list with potential nested complex objects.

        Args:
            obj: List to serialize

        Returns:
            List with all values serialized
        """
        result = []
        for item in obj:
            try:
                result.append(self.default(item))
            except TypeError:
                # If we can't serialize it, skip it or convert to string
                result.append(str(item))
        return result

    def _serialize_object_with_dict(self, obj: object) -> dict[str, Any]:
        """Serialize an object that has a __dict__ attribute.

        Args:
            obj: Object with __dict__ attribute

        Returns:
            Dictionary representation of the object

        Raises:
            TypeError: If the object has no serializable attributes
        """
        result = {}
        has_serializable_attrs = False

        for key, value in obj.__dict__.items():
            # Skip private attributes
            if key.startswith("_"):
                continue

            # Recursively serialize nested objects
            try:
                result[key] = self.default(value)
                has_serializable_attrs = True
            except TypeError:
                # If we can't serialize it, skip it or convert to string
                result[key] = str(value)
                has_serializable_attrs = True

        # If the object has no serializable attributes, raise TypeError
        if not has_serializable_attrs:
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        return result


# Convenience function for easy use
def dumps_with_encoder(
    data: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = None,
    **kwargs: Any,
) -> str:
    """Convenience function to serialize data using CustomJSONEncoder.

    Args:
        data: Data to serialize
        ensure_ascii: Whether to escape non-ASCII characters
        indent: Indentation level for pretty printing
        **kwargs: Additional arguments to pass to json.dumps

    Returns:
        JSON string representation of the data
    """
    return json.dumps(
        data,
        cls=CustomJSONEncoder,
        ensure_ascii=ensure_ascii,
        indent=indent,
        **kwargs,
    )
