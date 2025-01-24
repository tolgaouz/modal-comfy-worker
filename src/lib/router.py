from fastapi import FastAPI, HTTPException
from modal import Function, exception, functions, App, Image, Volume
from typing import TypeVar, Generic
from pydantic import BaseModel
from functools import wraps
from .exceptions import ExecutionError

PayloadT = TypeVar("PayloadT", bound=BaseModel)


def create_run_job(
    app: App, image: Image, volumes: dict[str, Volume], run_job_function
):
    @app.function(
        image=image,
        volumes=volumes,
        container_idle_timeout=60 * 2,
    )
    @wraps(run_job_function)
    async def run_job(payload: dict):
        try:
            return await run_job_function(payload)
        except Exception as e:
            print("Error in run_job")
            raise ExecutionError(e)

    return run_job


class ModalRouter(Generic[PayloadT]):
    def __init__(
        self,
        app: App,
        image: Image,
        volumes: dict[str, Volume],
        run_job_function: Function,
        payload_type: type[PayloadT],
    ):
        self.app = app
        self.web_app = FastAPI()
        self.payload_type = payload_type
        self.image = image
        self.volumes = volumes

        # Create the run_job function using our helper
        self.run_job = create_run_job(app, image, volumes, run_job_function)

        # Register routes
        self._setup_routes()

    def _setup_routes(self):
        @self.web_app.post("/infer_sync")
        async def infer(payload: self.payload_type):
            try:
                execution_result = self.run_job.remote(payload)
                return execution_result
            except Exception as e:
                print("Error in infer", e)
                raise HTTPException(status_code=500, detail=str(e))

        @self.web_app.post("/infer_async")
        async def infer_async(payload: self.payload_type):
            try:
                call = await self.run_job.spawn(payload)
                return {"call_id": call.object_id}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.web_app.get("/status/{call_id}")
        async def status(call_id: str):
            function_call = functions.FunctionCall.from_id(call_id)
            try:
                result = function_call.get(timeout=5)
            except exception.OutputExpiredError:
                result = {"result": None, "status": "expired"}
            except TimeoutError:
                result = {"result": None, "status": "pending"}
            return {"result": result}

        @self.web_app.post("/cancel/{call_id}")
        async def cancel(call_id: str):
            function_call = functions.FunctionCall.from_id(call_id)
            function_call.cancel()
            return {"call_id": call_id}

    def asgi_app(self):
        return self.web_app
