import time
from typing import Any

import httpx

FATAL_AUTH = "access_token has expired"


class VKError(Exception):
    """API error with code and message."""

    def __init__(self, code: int, msg: str, params: dict | None = None):
        self.code = code
        self.msg = msg
        super().__init__(f"VK API error {code}: {msg}")


class TokenExpired(VKError):
    """Raised when the web token expired and no refresher fixed it."""


class Client:
    """Low-level HTTP client for api.vk.ru with throttling and retry."""

    def __init__(self, token: str, v: str = "5.199", delay: float = 0.35,
                 host: str = "api.vk.ru", timeout: float = 30,
                 on_token_expired=None):
        self.token = token
        self.v = v
        self.delay = delay
        self.host = host
        self.on_token_expired = on_token_expired
        self.calls = 0
        self._last = 0.0
        self._http = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/153.0.8010.12 Safari/537.36",
                "Origin": f"https://{host.split('.')[1]}.ru",
                "Referer": "https://vk.ru/",
            },
        )

    def close(self):
        """Close the underlying HTTP session."""
        self._http.close()

    def call(self, method: str, **params) -> dict:
        """Call a VK API method; auto-retries error 6, raises VKError."""
        code, msg = 0, ""
        for attempt in range(4):
            wait = self.delay - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.calls += 1
            r = self._http.post(
                f"https://{self.host}/method/{method}",
                data={**params, "access_token": self.token, "v": self.v},
            )
            j = r.json()
            err = j.get("error")
            if not err:
                return j["response"]
            code = err.get("error_code", 0)
            msg = err.get("error_msg", "")
            if code == 6 and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            if code == 5 and FATAL_AUTH in msg:
                if self.on_token_expired:
                    self.token = self.on_token_expired(self)
                    if self.token:
                        continue
                raise TokenExpired(5, msg)
            raise VKError(code, msg, err.get("request_params"))
        raise VKError(code, msg)

    def execute(self, code: str) -> Any:
        """Run execute code on the server (batch API calls)."""
        return self.call("execute", code=code)

