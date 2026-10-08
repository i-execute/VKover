import json
import time

import pytest

from vkover import VKover, VKError, TokenExpired
from vkover.handlers import Dispatcher, NewMessage, Typing, wrap
from vkover.models import Conversation, Message


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, data=None):
        self.requests.append((url, data))
        r = self.responses.pop(0)
        class R:
            def __init__(self, payload):
                self.payload = payload

            def json(self):
                return self.payload
        return R(r)


def make_vk(responses):
    vk = VKover.__new__(VKover)
    from vkover.client import Client
    vk.client = Client.__new__(Client)
    vk.client._http = FakeHTTP(responses)
    vk.client._refresh_lock = False
    vk.client._refresh_failures = 0
    vk.client.max_refresh_failures = 3
    vk.client.token = "tok"
    vk.client.v = "5.199"
    vk.client.delay = 0
    vk.client.calls = 0
    vk.client._last = 0.0
    vk.client.on_token_expired = None
    vk.client.host = "api.vk.ru"
    vk._me = None
    vk.refresher = None
    vk.dispatcher = Dispatcher()
    return vk


def ok(payload):
    return {"response": payload}


def test_send_returns_id():
    vk = make_vk([ok(12345)])
    assert vk.send(100, "hi") == 12345
    url, data = vk.client._http.requests[0]
    assert data["peer_id"] == 100
    assert data["message"] == "hi"
    assert "random_id" in data


def test_error_raises_vkerror():
    vk = make_vk([{"error": {"error_code": 15, "error_msg": "denied"}}])
    with pytest.raises(VKError) as e:
        vk.send(100, "hi")
    assert e.value.code == 15


def test_token_expired_raises():
    vk = make_vk([{"error": {"error_code": 5,
                             "error_msg": "User authorization failed: access_token has expired."}}])
    with pytest.raises(TokenExpired):
        vk.send(100, "hi")


def test_rate_limit_retry():
    flood = {"error": {"error_code": 6, "error_msg": "too many"}}
    vk = make_vk([flood, ok(77)])
    assert vk.send(1, "x") == 77
    assert vk.client.calls == 2


def test_conversations_parse():
    payload = {"count": 1, "items": [{
        "conversation": {"peer": {"id": 100, "type": "user"},
                         "unread_count": 2, "last_message_id": 10,
                         "in_read": 5, "out_read": 10},
        "last_message": {"text": "yo"},
    }]}
    vk = make_vk([ok(payload)])
    cs = vk.conversations()
    assert len(cs) == 1
    assert cs[0].peer_id == 100
    assert cs[0].kind == "user"
    assert cs[0].unread == 2


def test_history_parse():
    payload = {"count": 1, "items": [{
        "id": 1, "peer_id": 100, "from_id": 200, "date": 123,
        "text": "hello", "out": 1,
    }]}
    vk = make_vk([ok(payload)])
    ms = vk.history(100)
    assert ms[0].text == "hello"
    assert ms[0].out is True


def test_wrap_new_message():
    ev = wrap([4, 6692, 33, 100, 1791, "privet", {"title": " ... "}, {}])
    assert isinstance(ev, NewMessage)
    assert ev.message_id == 6692
    assert ev.peer_id == 100
    assert ev.text == "privet"
    assert ev.out is False


def test_wrap_typing():
    ev = wrap([61, 1129275309, 1])
    assert isinstance(ev, Typing)
    assert ev.user_id == 1129275309


def test_wrap_unknown():
    ev = wrap([601, 2, 1])
    assert type(ev).__name__ == "UnknownEvent"
    assert ev.code == 601


def test_dispatcher_typed():
    vk = make_vk([])
    got = []
    got_raw = []

    @vk.on(NewMessage)
    def h(ev):
        got.append(ev)

    @vk.on_raw
    def r(u):
        got_raw.append(u)

    vk.dispatcher.dispatch([4, 1, 0, 100, 1, "x"])
    assert len(got) == 1
    assert got[0].text == "x"
    assert got_raw[0][0] == 4


def test_request_raw():
    vk = make_vk([ok({"a": 1})])
    assert vk.request("users.get") == {"a": 1}
    url, data = vk.client._http.requests[0]
    assert "users.get" in url


def test_send_reaction_request():
    vk = make_vk([ok(1)])
    assert vk.send_reaction_request(100, 5, 3) == 1
    url, data = vk.client._http.requests[0]
    assert data["cmid"] == 5
    assert data["reaction_id"] == 3


def test_forward_request():
    vk = make_vk([ok(9)])
    vk.forward_request(100, [11, 12], "look")
    _, data = vk.client._http.requests[0]
    assert data["forward_messages"] == "id=11,id=12"


def test_edit_message_request():
    vk = make_vk([ok(1)])
    vk.edit_message_request(100, 55, "new text")
    _, data = vk.client._http.requests[0]
    assert data["message_id"] == 55
    assert data["message"] == "new text"
