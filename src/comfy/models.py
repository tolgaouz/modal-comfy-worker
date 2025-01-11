from typing import Optional, Callable, Dict
from pydantic import BaseModel


class ExecutionData(BaseModel):
    prompt: Dict
    process_id: str


class ExecutionCallbacks(BaseModel):
    on_error: Optional[Callable[[Dict], None]] = None
    on_done: Optional[Callable[[Dict], None]] = None
    on_progress: Optional[Callable[[str, Dict, Optional[str]], None]] = None
    on_start: Optional[Callable[[Dict], None]] = None
    on_ws_message: Optional[Callable[[str, Dict], None]] = None


class Input(BaseModel):
    prompt: dict
    client_id: str
    process_id: str
    connection_url: Optional[str] = None


class PerformanceMetrics(BaseModel):
    execution_time: int
    execution_delay_time: int
    server_connection_time: Optional[int] = None


class BaseWorkerResponse(BaseModel):
    client_id: str
    process_id: str
    performance_metrics: PerformanceMetrics
