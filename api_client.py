import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


class APIError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(f"API error {status_code}: {detail}")


class SessionExpired(APIError):
    def __init__(self, detail="Tu sesión venció. Inicia sesión nuevamente."):
        super().__init__(401, detail)


class APIClient:
    def __init__(self, base_url, token=None, timeout=150):
        self.base_url = base_url.rstrip("/")
        self.token, self.timeout = token, timeout

    def _open(self, method, path, data=None):
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.base_url + path, data=None if data is None else json.dumps(data).encode(), headers=headers, method=method)
        try:
            return urlopen(request, timeout=self.timeout)
        except HTTPError as error:
            try:
                detail = json.loads(error.read()).get("detail", "La API rechazó la solicitud")
            except (ValueError, AttributeError):
                detail = "La API rechazó la solicitud"
            if error.code == 401:
                raise SessionExpired(str(detail)) from error
            raise APIError(error.code, str(detail)) from error
        except (URLError, OSError, TimeoutError) as error:
            raise APIError(0, "No se pudo conectar con la API. Intenta nuevamente.") from error

    def _request(self, method, path, data=None, raw=False):
        try:
            with self._open(method, path, data) as response:
                body = response.read()
            if raw:
                return body.decode("utf-8")
            return json.loads(body) if body else None
        except (OSError, TimeoutError) as error:
            raise APIError(0, "La conexión con la API se interrumpió") from error
        except (ValueError, UnicodeDecodeError) as error:
            raise APIError(502, "La API devolvió una respuesta inválida") from error

    def health(self):
        return self._request("GET", "/ready")

    def login(self, email, password):
        self.token = None
        response = self._request("POST", "/auth/login", {"email": email, "password": password})
        self.token = response["access_token"]
        return response

    def me(self):
        return self._request("GET", "/auth/me")

    def create_conversation(self):
        return self._request("POST", "/conversations", {})

    def conversation(self, conversation_id):
        return self._request("GET", f"/conversations/{conversation_id}")

    def list_conversations(self, limit=50, offset=0, archived=False):
        return self._request("GET", "/conversations?" + urlencode({"limit": limit, "offset": offset, "archived": str(archived).lower()}))

    def update_conversation(self, conversation_id, **changes):
        return self._request("PATCH", f"/conversations/{conversation_id}", changes)

    def delete_conversation(self, conversation_id):
        return self._request("DELETE", f"/conversations/{conversation_id}")

    def export_conversation(self, conversation_id):
        return self._request("GET", f"/conversations/{conversation_id}/export", raw=True)

    def get_messages(self, conversation_id, limit=50, before_id=None):
        params = {"limit": limit}
        if before_id is not None:
            params["before_id"] = before_id
        return self._request("GET", f"/conversations/{conversation_id}/messages?" + urlencode(params))

    def stream_chat(self, conversation_id, content, request_id=None):
        completed = False
        try:
            with self._open("POST", f"/conversations/{conversation_id}/chat", {"content": content, "request_id": str(request_id or uuid4())}) as response:
                for line in response:
                    if line.startswith(b"data: "):
                        event = json.loads(line[6:])
                        if event.get("type") in ("done", "error"):
                            completed = True
                        yield event
            if not completed:
                raise APIError(502, "La respuesta se interrumpió. El historial conserva los mensajes recibidos.")
        except (OSError, TimeoutError) as error:
            raise APIError(0, "Se interrumpió la conexión durante la respuesta") from error
        except (ValueError, UnicodeDecodeError) as error:
            raise APIError(502, "El flujo de respuesta no es válido") from error

    def list_memories(self):
        return self._request("GET", "/memories")

    def search_memories(self, query, limit=5):
        return self._request("POST", "/memories/search", {"query": query, "limit": limit})

    def save_memory(self, memory_text):
        return self._request("POST", "/memories", {"memory_text": memory_text})

    def update_memory(self, memory_id, memory_text):
        return self._request("PATCH", f"/memories/{memory_id}", {"memory_text": memory_text})

    def delete_memory(self, memory_id):
        return self._request("DELETE", f"/memories/{memory_id}")

    def tool_history(self, conversation_id):
        return self._request("GET", f"/conversations/{conversation_id}/tools")

    def actions(self, conversation_id):
        return self._request("GET", f"/conversations/{conversation_id}/actions")

    def decide_action(self, conversation_id, action_id, decision):
        return self._request("POST", f"/conversations/{conversation_id}/actions/{action_id}/{decision}", {})
