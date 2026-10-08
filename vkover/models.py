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
class ReactionUpdate:
    peer_id: int
    cmid: int
    reaction_id: int
    user_id: int
    removed: bool = False
    old_reaction_id: int = 0
    raw: list = field(default_factory=list)


@dataclass
class Event:
    code: int
    fields: list[Any]
    ts: int = 0

    @property
    def message(self) -> "Message":
        """Message object for code 4/5 events (fields exclude the code)."""
        f = self.fields
        return Message(
            id=f[0],
            peer_id=f[2] if len(f) > 2 else 0,
            from_id=(f[-1] if isinstance(f[-1], int) else 0),
            date=(f[3] if len(f) > 3 and isinstance(f[3], int) else 0),
            out=bool(f[1] & 2) if len(f) > 1 and isinstance(f[1], int) else False,
            text=(f[4] if len(f) > 4 and isinstance(f[4], str) else ""),
            raw={"code": self.code, "fields": f},
        )

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

    @property
    def reaction(self) -> ReactionUpdate | None:
        """Reaction event (code 601) — set, changed or removed."""
        if self.code != 601 or len(self.fields) < 6:
            return None
        f = self.fields
        etype = f[0]
        removed = etype in (2, 3)
        old = f[10] if (etype == 2 and len(f) > 10) else 0
        return ReactionUpdate(
            peer_id=f[1], cmid=f[2], reaction_id=f[6] if len(f) > 6 else f[3],
            user_id=f[9] if len(f) > 9 else 0,
            removed=removed, old_reaction_id=old, raw=f,
        )

    @property
    def is_reaction(self) -> bool:
        return self.code == 601
