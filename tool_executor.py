import json
from typing import Dict, Callable, Any

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

        try:
            result = self._registry[fn_name](**args)
            return result if isinstance(result, (dict, list)) else {"result": result}
        except Exception as e:
            return {"error": f"Error executing '{fn_name}': {str(e)}"}