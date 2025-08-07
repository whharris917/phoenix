"""
Provides common, stateless utility functions used across the application.

This module is a collection of simple, reusable helper functions that do not
fit into a more specific module and have no external dependencies other than
standard Python libraries.
"""
from datetime import datetime
from tracer import trace
from typing import Any

@trace
def get_timestamp() -> str:
    """
    Generates a formatted, uppercase timestamp string.

    Returns:
        A string representing the current time in the format 'DDMMMYYYY_HHMMSSAM/PM',
        e.g., '07AUG2025_014830PM'.
    """
    timestamp = datetime.now().strftime("%d%b%Y_%I%M%S%p").upper()
    return timestamp
