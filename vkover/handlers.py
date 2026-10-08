from collections import defaultdict

from .models import Event

NEW_MESSAGE = 4
EDIT_MESSAGE = 5
READ_INCOMING = 6
READ_OUTGOING = 7
USER_ONLINE = 8
USER_OFFLINE = 9
DIALOG_FLAGS = 10
MESSAGE_FLAGS = 11
UNREAD_COUNT_CHANGED = 12
TYPING_USER = 61
TYPING_CHAT = 62
TYPING_VOICE = 65
REACTION = 601
REACTIONS_COUNTER = 602

NAMES = {
    NEW_MESSAGE: "new_message",
    EDIT_MESSAGE: "edit_message",
    READ_INCOMING: "read_incoming",
    READ_OUTGOING: "read_outgoing",
    USER_ONLINE: "user_online",
    USER_OFFLINE: "user_offline",
    DIALOG_FLAGS: "dialog_flags",
    MESSAGE_FLAGS: "message_flags",
    UNREAD_COUNT_CHANGED: "unread_count_changed",
    TYPING_USER: "typing_user",
    TYPING_CHAT: "typing_chat",
    TYPING_VOICE: "typing_voice",
    REACTION: "reaction",
    REACTIONS_COUNTER: "reactions_counter",
}


class UnknownEvent(Event):
    """Raw event delivered when no typed class matches."""

    pass


class NewMessage(Event):
    """code 4: a message arrived (or was sent by self)."""

    @property
    def message_id(self) -> int:
        return self.fields[0]

    @property
    def flags(self) -> int:
        return self.fields[1]

    @property
    def peer_id(self) -> int:
        return self.fields[2]

    @property
    def timestamp(self) -> int:
        return self.fields[3]

    @property
    def text(self) -> str:
        for f in self.fields[4:]:
            if isinstance(f, str):
                return f
        return ""

    @property
    def out(self) -> bool:
        return bool(self.flags & 128)


class Typing(Event):
    """code 61/62/65: user is typing text/voice."""

    @property
    def user_id(self) -> int:
        return self.fields[0]

    @property
    def peer_id(self) -> int | None:
        if self.code == TYPING_CHAT and len(self.fields) > 1:
            return self.fields[1]
        return None


class ReadIn(Event):
    """code 6: incoming messages read up to local_id."""

    @property
    def peer_id(self) -> int:
        return self.fields[0]

    @property
    def local_id(self) -> int:
        return self.fields[1]


TYPED = {
    NEW_MESSAGE: NewMessage,
    TYPING_USER: Typing,
    TYPING_CHAT: Typing,
    TYPING_VOICE: Typing,
    READ_INCOMING: ReadIn,
}


def wrap(u: list) -> Event:
    """Wrap a raw update list into a typed event or UnknownEvent."""
    code = u[0]
    cls = TYPED.get(code, UnknownEvent)
    return cls(code=code, fields=list(u[1:]))


class Dispatcher:
    """Telethon-style dispatcher: typed handlers + raw handlers."""

    def __init__(self):
        self._typed: dict[type, list] = defaultdict(list)
        self._raw: list = []

    def on(self, event_cls):
        """Register a handler for a typed event class."""
        def deco(fn):
            self._typed[event_cls].append(fn)
            return fn
        return deco

    def on_raw(self, fn):
        """Register a raw handler receiving every update as a list."""
        self._raw.append(fn)
        return fn

    def dispatch(self, u: list):
        """Dispatch one raw update to matching handlers."""
        ev = wrap(u)
        for fn in self._typed.get(type(ev), []):
            fn(ev)
        for fn in self._raw:
            fn(u)
