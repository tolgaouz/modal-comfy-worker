class ComfyUIError(Exception):
    """Base exception for all ComfyUI related errors"""

    def __init__(self, message: str):
        super().__init__(message)


class ServerStartupError(ComfyUIError):
    """Raised when the ComfyUI server fails to start"""

    pass


class ExecutionError(ComfyUIError):
    """Raised when a ComfyUI execution fails"""

    pass


class WebSocketError(ComfyUIError):
    """Raised when there's an error with WebSocket communication"""

    pass
