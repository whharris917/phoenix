"""
Defines the high-level data structures for managing a user's session.

This module contains the Pydantic models that encapsulate the complete state
of a single, active user session, bundling together all the necessary service
proxies and managers required for the application's logic to operate.
"""
from pydantic import BaseModel, ConfigDict
from memory_manager import MemoryManager
from proxies import HavenProxyWrapper


class ActiveSession(BaseModel):
    """
    Represents a live user session with all its associated stateful objects.

    This model acts as a "context object" that is passed through the core
    application logic, providing a clean and organized way to access all
    session-specific components.
    """

    # This config allows the model to handle complex, non-pydantic
    # objects like MemoryManager without validation errors.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # A proxy wrapper for sending messages to this specific session in the Haven.
    chat: HavenProxyWrapper
    # An instance of the MemoryManager, scoped to this specific session.
    memory: MemoryManager
    # The unique, persistent name of the session (e.g., 'Session_07AUG2025_...').
    name: str
