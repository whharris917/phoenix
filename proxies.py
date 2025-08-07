"""
Provides a client-side abstraction for interacting with the remote Haven service.

This module contains proxy wrappers that act as local stand-ins for remote
objects, simplifying the interaction between the main application and the
persistent Haven service. It ensures safe, session-aware communication and
abstracts away the details of the remote procedure calls.
"""
import logging
from tracer import trace
from typing import Any

class HavenProxyWrapper:
    """
    Acts as a near-perfect drop-in replacement for a local chat session object.
    It holds a reference to the main Haven proxy and a specific session name,
    making remote calls appear as local method calls.
    """
    @trace
    def __init__(self, haven_service_proxy: Any, session_name: str):
        """
        Initializes the proxy wrapper.

        Args:
            haven_service_proxy: The main proxy object connected to the Haven service.
            session_name: The specific session this wrapper will interact with.
        """
        self.haven = haven_service_proxy
        self.session = session_name

    @trace
    def send_message(self, prompt: str) -> Any:
        """
        Forwards a prompt to the remote Haven service for a specific session.

        This method mimics the signature of the generative model's `send_message`
        but handles the remote call, data marshalling, and error handling.

        Args:
            prompt: The user's prompt text to send to the model.

        Returns:
            A mock response object with a `.text` attribute on success.

        Raises:
            RuntimeError: If the remote call to the Haven service returns an error.
        """
        response_dict = self.haven.send_message(self.session, prompt)

        class MockResponse:
            def __init__(self, text: str):
                self.text = text

        if response_dict and response_dict.get("status") == "success":
            return MockResponse(response_dict.get("text", ""))
        else:
            error_message = response_dict.get("message", "Unknown error in Haven.")
            logging.error(f"Error from Haven send_message for session '{self.session}': {error_message}")
            raise RuntimeError(f"Haven service failed for session '{self.session}': {error_message}")
