import json
from typing import Dict, Callable, Any

from api_client import SessionExpired
from pydantic import ValidationError
from tool_models import TOOL_ARGUMENT_MODELS


class ToolExecutor:
    """Gestiona el registro y ejecución dinámica de funciones para el LLM."""

    def __init__(self):
        self._registry: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable):
        self._registry[name] = func

    def execute(self, fn_name: str, args_json: str) -> dict:
        if fn_name not in self._registry:
            return {"error": f"Unknown tool '{fn_name}'"}

        try:
            args = json.loads(args_json)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON arguments: {str(e)}"}

        if not isinstance(args, dict):
            return {"error": "Tool arguments must be an object."}
        try:
            if fn_name in TOOL_ARGUMENT_MODELS:
                args = TOOL_ARGUMENT_MODELS[fn_name].model_validate(args).model_dump()
        except ValidationError as error:
            return {"error": "Invalid tool arguments", "details": error.errors(include_input=False, include_context=False)}

        try:
            result = self._registry[fn_name](**args)
            return result if isinstance(result, (dict, list)) else {"result": result}
        except Exception as e:
            if isinstance(e, SessionExpired):
                raise
            return {"error": f"Error executing '{fn_name}': {str(e)}"}
