import time

from .auth import TokenRefresher
from .client import Client, TokenExpired
from .longpoll import LongPoll
from .models import Conversation, Message
from .handlers import Dispatcher, wrap


class VKover:
    """High-level VK user-bot client: API methods + dispatcher + long poll."""

    def __init__(self, token: str, token_refresher: TokenRefresher | None = None,
                 v: str = "5.199", delay: float = 0.35):
        self.refresher = token_refresher
        self.client = Client(token, v=v, delay=delay,
                             on_token_expired=refresher.hook() if refresher else None)
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
        """Full messages.send response (not just id)."""
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                message=text, **kw)

    def edit_message_request(self, peer_id: int, message_id: int, text: str, **kw) -> int:
        """Edit own message text."""
        return self.client.call("messages.edit", peer_id=peer_id,
                                message_id=message_id, message=text, **kw)

    def delete_message_request(self, message_ids: list[int], **kw) -> dict:
        """Delete messages by ids."""
        return self.client.call("messages.delete",
                                message_ids=",".join(map(str, message_ids)), **kw)

    def send_reaction_request(self, peer_id: int, cmid: int, reaction_id: int) -> int:
        """Set a reaction on a message (None id = 0 removes)."""
        return self.client.call("messages.setReaction", peer_id=peer_id,
                                cmid=cmid, reaction_id=reaction_id)

    def delete_reaction_request(self, peer_id: int, cmid: int) -> int:
        """Remove a reaction from a message."""
        return self.client.call("messages.setReaction", peer_id=peer_id,
                                cmid=cmid, reaction_id=0)

    def get_reactions_request(self, peer_id: int, cmid: int) -> dict:
        """Who reacted to a message."""
        return self.client.call("messages.getMessagesReactions",
                                peer_id=peer_id, cmid=cmid, extended=1)

    def send_sticker_request(self, peer_id: int, sticker_id: int, **kw) -> dict:
        """Send a sticker by id."""
        return self.client.call("messages.send", peer_id=peer_id,
                                random_id=int(time.time() * 1000) % 2**31,
                                sticker_id=sticker_id, **kw)

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

    def users(self, ids: list[int]) -> list[dict]:
        """Fetch user profiles."""
        return self.client.call("users.get", user_ids=",".join(map(str, ids)))
