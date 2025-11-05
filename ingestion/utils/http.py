import json
import time
from typing import Any, Dict, Optional

import requests
from requests import Response
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class HttpError(Exception):
    pass


class HttpClient:
    def __init__(
        self,
        user_agent: str = "CROcashi-Ingestion/1.0",
        requests_per_second: float = 2.0,
        timeout_seconds: float = 20.0,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.session = requests.Session()
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_interval = 1.0 / max(requests_per_second, 0.001)
        self._last_request_time = 0.0
        self.default_headers = {"User-Agent": self.user_agent}
        if extra_headers:
            self.default_headers.update(extra_headers)

    def _rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_time = time.time()

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception_type((requests.RequestException, HttpError)),
    )
    def get(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Response:
        self._rate_limit()
        resp = self.session.get(url, params=params, headers={**self.default_headers, **(headers or {})}, timeout=self.timeout_seconds)
        if resp.status_code >= 500:
            raise HttpError(f"Server error {resp.status_code} for {url}")
        return resp

    @staticmethod
    def json_or_text(resp: Response) -> Any:
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct or resp.text.strip().startswith("{"):
            try:
                return resp.json()
            except json.JSONDecodeError:
                return resp.text
        return resp.text


