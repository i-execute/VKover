from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    id: int
    peer_id: int
    from_id: int
    date: int
    text: str
    out: bool = False
    conversation_message_id: int = 0
    reply_message: dict | None = None
    attachments: list[dict] = field(default_factory=list)
    fwd_messages: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict) -> "Message":
        return cls(
            id=d.get("id", 0),
            peer_id=d.get("peer_id", 0),
            from_id=d.get("from_id", d.get("user_id", 0)),
            date=d.get("date", 0),
            text=d.get("text", ""),
            out=bool(d.get("out", 0)),
            conversation_message_id=d.get("conversation_message_id", 0),
            reply_message=d.get("reply_message"),
            attachments=d.get("attachments", []) or [],
            fwd_messages=d.get("fwd_messages", []) or [],
            raw=d,
        )


@dataclass
class Conversation:
    peer_id: int
    kind: str
    title: str
    unread: int
    last_message_id: int
    in_read: int
    out_read: int
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict) -> "Conversation":
        """Parse one item of messages.getConversations."""
        conv = d.get("conversation", d)
        peer = conv.get("peer", {})
        last = d.get("last_message", {}) or {}
        return cls(
            peer_id=peer.get("id", last.get("peer_id", 0)),
            kind=peer.get("type", "user" if last else ""),
            title=conv.get("chat_settings", {}).get("title", "") or last.get("title", ""),
            unread=conv.get("unread_count", 0),
            last_message_id=conv.get("last_message_id", 0),
            in_read=conv.get("in_read", 0),
            out_read=conv.get("out_read", 0),
            raw=d,
        )


@dataclass
class Event:
    code: int
    fields: list[Any]
    ts: int = 0

    @property
    def is_new_message(self) -> bool:
        return self.code == 4

    @property
    def is_edit(self) -> bool:
        return self.code == 5

    @property
    def is_read(self) -> bool:
        return self.code in (6, 7)

    @property
    def is_typing(self) -> bool:
        return self.code in (61, 65)
