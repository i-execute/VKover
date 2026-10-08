import time

import httpx

from .client import TokenExpired
from .models import Event


class LongPoll:
    MODE = 234
    VERSION = 3

    def __init__(self, client, wait: int = 25):
        self.client = client
        self.wait = wait
        self.server = self.key = None
        self.ts = self.pts = 0
        self._http = httpx.Client(timeout=wait + 20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/153.0.8010.12 Safari/537.36",
        })

    def connect(self):
        r = self.client.call("messages.getLongPollServer",
                             need_pts=1, lp_version=self.VERSION)
        self.server = r["server"]
        self.key = r["key"]
        self.ts = r["ts"]
        self.pts = r.get("pts", 0)

    def events(self):
        if not self.server:
            self.connect()
        while True:
            try:
                r = self._http.get(
                    f"https://{self.server}",
                    params={"act": "a_check", "key": self.key, "ts": self.ts,
                            "wait": self.wait, "mode": self.MODE,
                            "version": self.VERSION},
                ).json()
            except (httpx.HTTPError, ValueError):
                time.sleep(2)
                try:
                    self.connect()
                except TokenExpired:
                    self._http.close()
                    raise
                continue

            if "failed" in r:
                code = r["failed"]
                if code == 1:
                    self.ts = r["ts"]
                    continue
                try:
                    self.connect()
                except TokenExpired:
                    self._http.close()
                    raise
                continue

            self.ts = r["ts"]
            if r.get("pts"):
                self.pts = r["pts"]
            for u in r.get("updates", []):
                yield Event(code=u[0], fields=list(u[1:]), ts=self.ts)

    def close(self):
        self._http.close()
