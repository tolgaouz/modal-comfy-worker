class WebSocketError(Exception):
    """Base exception for WebSocket related errors"""

    pass


class MessageSendError(WebSocketError):
    """Raised when a WebSocket message fails to send"""

    def __init__(self, process_id: str, original_error: Exception):
        self.process_id = process_id
        self.original_error = original_error
        super().__init__(
            f"Failed to send websocket message for {process_id}: {str(original_error)}"
        )
