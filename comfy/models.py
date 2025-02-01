from typing import Optional, Callable, Dict
from pydantic import BaseModel
from ..lib.exceptions import ComfyUIError


class ExecutionData(BaseModel):
    prompt: Dict
    process_id: str


class ExecutionCallbacks(BaseModel):
    on_error: Optional[Callable[[Dict], None]] = None
    on_done: Optional[Callable[[Dict], None]] = None
    on_progress: Optional[Callable[[str, Dict, Optional[str]], None]] = None
    on_start: Optional[Callable[[Dict], None]] = None
    on_ws_message: Optional[Callable[[str, Dict], None]] = None


class ExecutionResult(BaseModel):
    prompt_id: str
    queue_duration: int


class PerformanceMetrics(BaseModel):
    execution_time: int
    execution_delay_time: int
    server_connection_time: Optional[int] = None


class BaseWorkerResponse(BaseModel):
    client_id: str
    process_id: str
    performance_metrics: PerformanceMetrics
    error: Optional[str] = None

    @classmethod
    def from_error(
        cls, error: ComfyUIError, client_id: str, process_id: str
    ) -> "BaseWorkerResponse":
        return cls(
            client_id=client_id,
            process_id=process_id,
            performance_metrics=PerformanceMetrics(
                execution_time=0, execution_delay_time=0
            ),
            error=str(error),
        )


class QueuePromptData(BaseModel):
    prompt: dict
    client_id: str
