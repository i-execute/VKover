import json
import time

from .auth import TokenRefresher
from .client import Client, TokenExpired
from .formatting import html_to_format_data
from .longpoll import LongPoll
from .models import Conversation, Message
from .handlers import Dispatcher, wrap
from .calls import CallsCache


REACTIONS = {
    1: "❤", 2: "🔥", 3: "😂", 4: "👍", 5: "💩", 6: "❓", 7: "😭", 8: "😡",
    9: "👎", 10: "😁", 11: "🤔", 12: "🙏", 13: "😘", 14: "😍", 15: "🎉", 16: "🤡",
}
REACTIONS_BY_EMOJI = {v: k for k, v in REACTIONS.items()}


def _resolve_reaction(reaction: int | str) -> int:
    """Reaction id from int id, emoji str, or hex codepoint str (U+1F525)."""
    if isinstance(reaction, int):
        return reaction
    r = reaction.strip()
    if r in REACTIONS_BY_EMOJI:
        return REACTIONS_BY_EMOJI[r]
    if r.upper().startswith("U+"):
        try:
            cp = chr(int(r[2:], 16))
        except ValueError:
            raise ValueError(f"bad codepoint: {r}")
        if cp in REACTIONS_BY_EMOJI:
            return REACTIONS_BY_EMOJI[cp]
    raise ValueError(
        f"unknown reaction {reaction!r}; available: "
        + " ".join(f"{i}={e}" for i, e in REACTIONS.items())
    )


class VKover:
    """High-level VK user-bot client: API methods + dispatcher + long poll."""

    def __init__(self, token: str, token_refresher: TokenRefresher | None = None,
                 v: str = "5.199", delay: float = 0.35):
        self.refresher = token_refresher
        self.client = Client(token, v=v, delay=delay,
                             on_token_expired=token_refresher.hook() if token_refresher else None)
        self.dispatcher = Dispatcher()
        self._me = None
        self._lp = None

    @classmethod
    def from_files(cls, token_file: str, profile_dir: str | None = None,
                   v: str = "5.199") -> "VKover":
        """Build a client from web_token.json with optional auto-refresh."""
        import json
        with open(token_file, encoding="utf-8") as f:
            tok = json.load(f)["access_token"]
        refresher = TokenRefresher(profile_dir or ".", token_file) if profile_dir else None
        return cls(tok, token_refresher=refresher, v=v)

    @property
    def me(self) -> dict:
        """Current user (users.get, cached)."""
        if self._me is None:
            self._me = self.client.call("users.get")[0]
        return self._me

    def longpoll(self) -> LongPoll:
        """Fresh Long Poll session bound to this client."""
        return LongPoll(self.client)

    def on(self, event_cls):
        """Decorator: register a typed event handler."""
        return self.dispatcher.on(event_cls)

    def on_raw(self, fn):
        """Decorator: register a raw update handler."""
        return self.dispatcher.on_raw(fn)

    def run(self):
        """Listen to Long Poll forever; auto-refreshes token on expiry."""
        while True:
            self._lp = LongPoll(self.client)
            try:
                for u in self._lp.events():
                    self.dispatcher.dispatch(u)
            except TokenExpired:
                if not self.refresher:
                    self.close()
                    raise
                tok = None
                try:
                    tok = self.refresher.refresh()
                except Exception:
                    tok = None
                if not tok:
                    self.close()
                    raise
                self.client.token = tok
                self.client._refresh_failures = 0
                continue
            finally:
                if self._lp:
                    try:
                        self._lp.close()
                    except Exception:
                        pass
                self._lp = None
            break
        self.close()

    def close(self):
        """Close HTTP sessions."""
        if self._lp:
            self._lp.close()
        self.client.close()

    def send(self, peer_id: int, text: str, **kw) -> int:
        """Send a text message; returns message id."""
        r = self.client.call("messages.send", peer_id=peer_id,
                             random_id=int(time.time() * 1000) % 2**31,
                             message=text, **kw)
        return r if isinstance(r, int) else r.get("response", r)

    def request(self, method: str, **params):
        """Raw API call with any method name."""
        return self.client.call(method, **params)

    def send_message_request(self, peer_id: int, text: str = "", **kw) -> dict:
        """Full messages.send response (not just id). HTML tags become format_data."""
        if "<" in text:
            text, fd = html_to_format_data(text)
            if fd and "format_data" not in kw:
                kw["format_data"] = json.dumps(fd, ensure_ascii=False)
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                message=text, **kw)

    def edit_message_request(self, peer_id: int, message_id: int, text: str, **kw) -> int:
        """Edit own message text. HTML tags become format_data."""
        if "<" in text:
            text, fd = html_to_format_data(text)
            if fd and "format_data" not in kw:
                kw["format_data"] = json.dumps(fd, ensure_ascii=False)
        return self.client.call("messages.edit", peer_id=peer_id,
                                message_id=message_id, message=text, **kw)

    def delete_message_request(self, message_ids: list[int], **kw) -> dict:
        """Delete messages by ids."""
        return self.client.call("messages.delete",
                                message_ids=",".join(map(str, message_ids)), **kw)

    def forward_message_request(self, peer_id: int, message_ids: list[int],
                                text: str = "", **kw) -> int:
        """Forward messages to a peer."""
        if "<" in text:
            text, fd = html_to_format_data(text)
            if fd and "format_data" not in kw:
                kw["format_data"] = json.dumps(fd, ensure_ascii=False)
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                forward_messages=",".join(map(str, message_ids)),
                                message=text, **kw)

    def send_sticker_request(self, peer_id: int, sticker_id: int, **kw) -> int:
        """Send a sticker by its id."""
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                sticker_id=sticker_id, message="", **kw)

    def resolve_stickerpack_request(self, product_id: int) -> dict:
        """Resolve sticker pack: keywords map with all sticker ids/images."""
        return self.client.call("store.getStickersKeywords",
                                products_ids=product_id, need_stickers=1,
                                all_products=1)

    def get_stickerpack_ids(self, product_id: int) -> list[int]:
        """All sticker ids in a pack."""
        r = self.resolve_stickerpack_request(product_id)
        ids: list[int] = []
        for entry in r.get("dictionary", []):
            for s in entry.get("user_stickers", []) or entry.get("stickers", []):
                sid = s.get("sticker_id")
                if sid and sid not in ids:
                    ids.append(sid)
        return ids

    def get_recent_stickers_request(self) -> dict:
        """Recently used stickers."""
        return self.client.call("messages.getRecentStickers")

    def get_reactions_assets_request(self) -> dict:
        """Available reaction assets."""
        return self.client.call("messages.getReactionsAssets")

    def send_reaction_request(self, peer_id: int, cmid: int,
                             reaction: int | str) -> int:
        """Set a reaction on a message.

        reaction: id (1-16), emoji ("🔥") or codepoint ("U+1F525").
        Available: 1=❤ 2=🔥 3=😂 4=👍 5=💩 6=❓ 7=😭 8=😡
        9=👎 10=😁 11=🤔 12=🙏 13=😘 14=😍 15=🎉 16=🤡
        """
        return self.client.call("messages.sendReaction", peer_id=peer_id,
                                cmid=cmid, reaction_id=_resolve_reaction(reaction))

    def set_reaction_request(self, peer_id: int, cmid: int,
                             reaction: int | str,
                             x_react: bool = True) -> int:
        """Set a reaction (incl. 9+ ids) on a message. See send_reaction_request."""
        return self.client.call("messages.sendReaction", peer_id=peer_id,
                                cmid=cmid, reaction_id=_resolve_reaction(reaction),
                                x_react=1 if x_react else 0)

    def remove_reaction_request(self, peer_id: int, cmid: int,
                                reaction_id: int | None = None) -> int:
        """Remove own reaction(s) from a message."""
        params = {"peer_id": peer_id, "cmid": cmid}
        if reaction_id is not None:
            params["reaction_id"] = reaction_id
        return self.client.call("messages.deleteReaction", **params)

    def delete_reaction_request(self, peer_id: int, cmid: int) -> int:
        """Remove a reaction from a message."""
        return self.client.call("messages.deleteReaction", peer_id=peer_id,
                                cmid=cmid)

    def get_reactions_request(self, peer_id: int, cmid: int) -> dict:
        """Who reacted to a message."""
        return self.client.call("messages.getMessagesReactions",
                                peer_id=peer_id, cmid=cmid, extended=1)

    def send_sticker_request(self, peer_id: int, sticker_id: int, **kw) -> dict:
        """Send a sticker by id."""
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                sticker_id=sticker_id, **kw)

    def search_music_request(self, query: str, count: int = 10) -> list[dict]:
        """Search VK audio.

        Returns list of {artist, title, id, owner_id, duration, access_key,
        attachment, has_cover, cover_url, download_url}."""
        r = self.client.call("audio.search", q=query, count=count)
        out = []
        for a in r.get("items", []):
            thumb = (a.get("album") or {}).get("thumb") or {}
            out.append({
                "artist": a.get("artist", ""),
                "title": a.get("title", ""),
                "id": a.get("id"),
                "owner_id": a.get("owner_id"),
                "duration": a.get("duration"),
                "access_key": a.get("access_key", ""),
                "attachment": (f"audio{a['owner_id']}_{a['id']}"
                               + (f"_{a['access_key']}" if a.get("access_key") else "")),
                "has_cover": bool(thumb),
                "cover_url": thumb.get("photo_600") or thumb.get("photo_300"),
                "download_url": a.get("url") or "",
            })
        return out

    def download_track_request(self, track: dict, out_path: str) -> str:
        """Download a search result track to an mp3 file (m3u8 + AES-128 + concat)."""
        import re as _re
        import subprocess as _sp
        import httpx as _hx
        if not track.get("download_url"):
            raise ValueError("track has no download_url")
        h = _hx.Client(headers={"User-Agent": "Mozilla/5.0"},
                       timeout=30, follow_redirects=True)

        def _get(url: str, tries: int = 4) -> bytes:
            import time as _time
            for i in range(tries):
                try:
                    return h.get(url).content
                except _hx.HTTPError:
                    _time.sleep(2 * (i + 1))
            raise _hx.ConnectTimeout(f"CDN unreachable: {url[:60]}")

        m3u = _get(track["download_url"]).decode("utf-8", "replace")
        base = track["download_url"].rsplit("/", 1)[0] + "/"
        key_m = _re.search(r'#EXT-X-KEY:METHOD=AES-128,URI="([^"]+)"', m3u)
        key = _get(key_m.group(1)) if key_m else None
        if key:
            from Crypto.Cipher import AES as _AES
            dec = _AES.new(key, _AES.MODE_ECB)
        out = b""
        enc = False
        for line in m3u.strip().split("\n"):
            line = line.strip()
            if line.startswith("#EXT-X-KEY:METHOD=AES-128"):
                enc = True
            elif line.startswith("#EXT-X-KEY:METHOD=NONE"):
                enc = False
            elif line and not line.startswith("#"):
                chunk = _get(base + line)
                if enc and key:
                    out += dec.decrypt(chunk)
                else:
                    out += chunk
        open(out_path, "wb").write(out)
        return out_path

    def download_cover_request(self, track: dict, out_path: str) -> str | None:
        """Download a track cover image; None if the track has no cover."""
        if not track.get("cover_url"):
            return None
        import httpx as _hx
        r = _hx.get(track["cover_url"],
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=30,
                    follow_redirects=True)
        open(out_path, "wb").write(r.content)
        return out_path

    def upload_photo_request(self, peer_id: int, path: str,
                             caption: str = "") -> str:
        """Upload a photo; returns the photo<owner>_<id> attachment string."""
        import time as _time
        import httpx as _hx
        r = self.client.call("photos.getMessagesUploadServer", peer_id=peer_id)
        with open(path, "rb") as f:
            data = f.read()
        up = None
        for attempt in range(4):
            try:
                resp = _hx.post(r["upload_url"],
                                files={"photo": (path.rsplit("/", 1)[-1], data,
                                                 "image/jpeg")},
                                timeout=90)
                up = resp.json()
                break
            except (ValueError, _hx.HTTPError):
                _time.sleep(2 * (attempt + 1))
        if not up or not up.get("photo") or up["photo"] == "[]":
            raise RuntimeError("photo upload failed")
        saved = self.client.call("photos.saveMessagesPhoto",
                                 server=up["server"], photo=up["photo"],
                                 hash=up["hash"])
        p = saved[0]
        return f"photo{p['owner_id']}_{p['id']}"

    def send_photo_request(self, peer_id: int, path: str, caption: str = "",
                           **kw) -> int:
        """Send a photo with a caption (HTML formatting supported)."""
        att = self.upload_photo_request(peer_id, path)
        text, fd = html_to_format_data(caption)
        if fd:
            kw.setdefault("format_data", json.dumps(fd, ensure_ascii=False))
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                message=text, attachment=att, **kw)

    def send_photos_request(self, peer_id: int, paths: list[str],
                            caption: str = "", **kw) -> int:
        """Send multiple photos as one album message (up to 10)."""
        atts = [self.upload_photo_request(peer_id, p) for p in paths]
        text, fd = html_to_format_data(caption)
        if fd:
            kw.setdefault("format_data", json.dumps(fd, ensure_ascii=False))
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                message=text, attachment=",".join(atts), **kw)

    def send_audio_request(self, peer_id: int, owner_id: int, audio_id: int,
                           access_key: str = "", text: str = "", **kw) -> int:
        """Send an audio track as attachment (HTML formatting in text)."""
        att = f"audio{owner_id}_{audio_id}" + (f"_{access_key}" if access_key else "")
        plain, fd = html_to_format_data(text)
        if fd:
            kw.setdefault("format_data", json.dumps(fd, ensure_ascii=False))
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                message=plain, attachment=att, **kw)

    def upload_doc_request(self, peer_id: int, name: str, data: bytes,
                           content_type: str = "text/plain") -> dict:
        """Upload a file for a chat; returns {id, owner_id, attachment}."""
        import io
        import httpx as _hx
        r = self.client.call("docs.getMessagesUploadServer", peer_id=peer_id,
                             type="doc")
        files = {"file": (name, io.BytesIO(data), content_type)}
        with _hx.Client(timeout=90) as c:
            up = c.post(r["upload_url"], files=files).json()
        d = self.client.call("docs.save", file=up["file"], title=name)
        d = d.get("doc", d)
        return {
            "id": d.get("id"),
            "owner_id": d.get("owner_id"),
            "attachment": f"doc{d['owner_id']}_{d['id']}",
        }

    def send_doc_request(self, peer_id: int, name: str, data: bytes,
                         text: str = "", **kw) -> int:
        """Upload and send a file in one call."""
        d = self.upload_doc_request(peer_id, name, data)
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                message=text, attachment=d["attachment"], **kw)

    def reply_request(self, peer_id: int, reply_to_cmid: int, text: str, **kw) -> dict:
        """Reply to a specific message."""
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                message=text, reply_to_cmid=reply_to_cmid, **kw)

    def forward_request(self, peer_id: int, fwd_message_ids: list[int],
                        text: str = "", **kw) -> dict:
        """Forward messages into a peer."""
        fwd = ",".join(f"id={i}" for i in fwd_message_ids)
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                message=text, forward_messages=fwd, **kw)

    def set_typing_request(self, peer_id: int, typing_type: str = "text") -> int:
        """Send an activity signal (text/voice/video)."""
        return self.client.call("messages.setActivity", peer_id=peer_id,
                                type=typing_type)

    def pin_message_request(self, peer_id: int, message_id: int, **kw) -> int:
        """Pin a message in a chat."""
        return self.client.call("messages.pin", peer_id=peer_id,
                                message_id=message_id, **kw)

    def unpin_message_request(self, peer_id: int, **kw) -> int:
        """Unpin a message in a chat."""
        return self.client.call("messages.unpin", peer_id=peer_id, **kw)

    def get_conversation_request(self, peer_id: int, **kw) -> dict:
        """Fetch conversation by peer id."""
        r = self.client.call("messages.getConversationsById",
                             peer_ids=peer_id, **kw)
        return r.get("items", [{}])[0]

    def search_messages_request(self, text: str, **kw) -> dict:
        """Global message search."""
        return self.client.call("messages.search", q=text, extended=1, **kw)

    def conversations(self, count: int = 20, offset: int = 0) -> list[Conversation]:
        """List dialogs."""
        r = self.client.call("messages.getConversations",
                             count=count, offset=offset, extended=1)
        return [Conversation.from_api(i) for i in r.get("items", [])]

    def history(self, peer_id: int, count: int = 50, offset: int = 0,
                rev: bool = False) -> list[Message]:
        """Message history for a peer."""
        r = self.client.call("messages.getHistory", peer_id=peer_id, count=count,
                             offset=offset, rev=int(rev), extended=0)
        return [Message.from_api(m) for m in r.get("items", [])]

    def mark_read(self, peer_id: int, up_to: int | None = None):
        """Mark dialog read."""
        p = {"peer_id": peer_id}
        if up_to:
            p["start_message_id"] = up_to
        return self.client.call("messages.markAsRead", **p)

    def create_web_call_request(self, group_id: int | None = None) -> dict:
        """Create a VK call; returns call_id, join_link, short_credentials."""
        p = {}
        if group_id:
            p["group_id"] = group_id
        return self.client.call("calls.start", **p)

    start_call_request = create_web_call_request

    def finish_web_call_request(self, call_id: str) -> bool:
        """Force-finish a VK call."""
        return bool(self.client.call("calls.forceFinish", call_id=call_id))

    finish_call_request = finish_web_call_request

    def calls(self, db=None) -> "CallsCache":
        """Local cache of active calls (no API list endpoint exists)."""
        cache = CallsCache(self, db)
        cache.load()
        return cache

    def users(self, ids: list[int]) -> list[dict]:
        """Fetch user profiles."""
        return self.client.call("users.get", user_ids=",".join(map(str, ids)))
