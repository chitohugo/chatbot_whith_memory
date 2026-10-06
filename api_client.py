import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class APIError(Exception):
    """Error returned by the chatbot API or raised while reaching it."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


class SessionExpired(APIError):
    """The API rejected the current access token."""

    def __init__(self, detail: str = "Session expired"):
        super().__init__(401, detail)


class APIClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        internal_key: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.internal_key = internal_key

    def login(self, email: str, password: str) -> dict[str, Any]:
        self.token = None
        response = self._request(
            "POST",
            "/auth/login",
            {"email": email, "password": password},
            authenticated=False,
        )
        self.token = response["access_token"]
        return response

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/auth/me")

    def create_conversation(self) -> dict[str, Any]:
        return self._request("POST", "/conversations", {})

    def list_conversations(self) -> list[dict[str, Any]]:
        return self._request("GET", "/conversations")

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"/conversations/{conversation_id}/messages",
        )

    def create_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/conversations/{conversation_id}/messages",
            {"role": role, "content": content},
        )

    def create_internal_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/conversations/{conversation_id}/messages/internal",
            {"role": role, "content": content},
            internal=True,
        )

    def delete_conversation(self, conversation_id: str) -> None:
        self._request("DELETE", f"/conversations/{conversation_id}")

    def search_memories(
        self,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        return self._request(
            "POST",
            "/memories/search",
            {"query": query, "limit": limit},
        )

    def save_memory(self, memory_text: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/memories",
            {"memory_text": memory_text},
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        internal: bool = False,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if internal and self.internal_key:
            headers["X-Internal-Request"] = self.internal_key

        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(request, timeout=30) as response:
                body = response.read()
        except HTTPError as exc:
            detail = self._error_detail(exc)
            if exc.code == 401:
                raise SessionExpired(detail) from exc
            raise APIError(exc.code, detail) from exc
        except URLError as exc:
            raise APIError(0, f"API unavailable: {exc.reason}") from exc

        if not body:
            return None

        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError(502, "Invalid response from API") from exc

    @staticmethod
    def _error_detail(error: HTTPError) -> str:
        try:
            body = error.read()
            payload = json.loads(body.decode("utf-8"))
            detail = payload.get("detail", payload)
            return str(detail)
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            return error.reason or "API request failed"
