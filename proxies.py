import logging


class HavenProxyWrapper:
    """
    Acts as a near-perfect drop-in replacement for a local chat session object.
    It holds a reference to the main Haven proxy and a specific session name.
    """

    def __init__(self, haven_service_proxy, session_name):
        self.haven = haven_service_proxy
        self.session = session_name

    def send_message(self, prompt):
        """
        Has the same signature as the original chat object's send_message.
        Calls the main Haven proxy's remote method, providing the session name it already knows.
        """
        response_dict = self.haven.send_message(self.session, prompt)

        class MockResponse:
            def __init__(self, text):
                self.text = text

        if response_dict and response_dict.get("status") == "success":
            return MockResponse(response_dict.get("text", ""))
        else:
            # Raise an exception instead of returning a mock response with an error.
            error_message = response_dict.get("message", "Unknown error in Haven.")
            logging.error(f"Error from Haven send_message for session '{self.session}': {error_message}")
            raise RuntimeError(f"Haven service failed for session '{self.session}': {error_message}")
