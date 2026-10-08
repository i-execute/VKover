import pytest

from vkover import VKover, TokenExpired
from vkover.client import Client
from tests.test_vkover import FakeHTTP, make_vk, ok


def expired():
    return {"error": {"error_code": 5,
                      "error_msg": "User authorization failed: access_token has expired."}}


def test_auto_refresh_success():
    vk = make_vk([])
    refreshed = []

    def hook(client):
        refreshed.append(client.token)
        return "newtok"

    vk.client.on_token_expired = hook
    vk.client._http.responses = [expired(), ok(42)]
    assert vk.send(1, "x") == 42
    assert vk.client.token == "newtok"
    assert len(refreshed) == 1


def test_auto_refresh_failure_raises():
    vk = make_vk([])
    vk.client.on_token_expired = lambda client: None
    vk.client._http.responses = [expired()]
    with pytest.raises(TokenExpired):
        vk.send(1, "x")


def test_refresh_failure_counter():
    vk = make_vk([])
    calls = []
    vk.client.on_token_expired = lambda client: calls.append(1) or None
    vk.client._http.responses = [expired(), expired(), expired(), expired()]
    with pytest.raises(TokenExpired):
        vk.send(1, "x")
    assert vk.client._refresh_failures == 1
    with pytest.raises(TokenExpired):
        vk.send(1, "x")
    with pytest.raises(TokenExpired):
        vk.send(1, "x")
    assert vk.client._refresh_failures == 3
    assert len(calls) == 3
    vk.client._http.responses = [expired()]
    with pytest.raises(TokenExpired):
        vk.send(1, "x")
    assert len(calls) == 3


def test_refresh_counter_resets_after_success():
    vk = make_vk([])
    state = {"n": 0}

    def hook(client):
        state["n"] += 1
        return "tok2" if state["n"] % 2 == 0 else None

    vk.client.on_token_expired = hook
    vk.client._http.responses = [expired(), ok(1), expired(), ok(2)]
    with pytest.raises(TokenExpired):
        vk.send(1, "a")
    assert vk.send(1, "a") == 1
    assert vk.client._refresh_failures == 0 or state["n"] % 2 == 1
    assert vk.send(1, "b") == 2


def test_no_hook_raises_immediately():
    vk = make_vk([])
    vk.client.on_token_expired = None
    vk.client._http.responses = [expired()]
    with pytest.raises(TokenExpired):
        vk.send(1, "x")
    assert vk.client._refresh_failures == 0


def test_auth_code_1110_triggers_refresh():
    vk = make_vk([])
    vk.client.on_token_expired = lambda client: "tok2"
    vk.client._http.responses = [
        {"error": {"error_code": 1110, "error_msg": "token expired"}},
        ok(7),
    ]
    assert vk.send(1, "x") == 7
