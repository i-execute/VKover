import json
import os
import time

TOKEN_KEY = "web_token:login:auth"


class TokenRefresher:
    def __init__(self, profile_dir: str, token_file: str):
        self.profile_dir = profile_dir
        self.token_file = token_file

    def read_cached(self) -> str | None:
        try:
            with open(self.token_file, encoding="utf-8") as f:
                return json.load(f)["access_token"]
        except (OSError, ValueError, KeyError):
            return None

    def refresh(self) -> str | None:
        tok = self._from_localstorage()
        if tok:
            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump({"access_token": tok}, f)
        return tok

    def _from_localstorage(self) -> str | None:
        from playwright.sync_api import sync_playwright

        leveldb = os.path.join(self.profile_dir, "Default", "Local Storage", "leveldb")
        if not os.path.isdir(leveldb):
            raise FileNotFoundError(f"no profile at {self.profile_dir}")
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                self.profile_dir,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto("https://vk.ru/", wait_until="domcontentloaded", timeout=60000)
                deadline = time.time() + 30
                while time.time() < deadline:
                    keys = page.evaluate("() => Object.keys(localStorage)")
                    for k in keys:
                        if TOKEN_KEY in k:
                            v = page.evaluate(f'() => localStorage.getItem("{k}")')
                            try:
                                return json.loads(v)["access_token"]
                            except (ValueError, KeyError, TypeError):
                                pass
                    time.sleep(2)
                return None
            finally:
                ctx.close()

    def hook(self):
        def _h(client):
            try:
                return self.refresh()
            except Exception:
                return None
        return _h
