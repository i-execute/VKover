import pytest

from vkover import CallsCache
from vkover.client import VKError


class FakeVK:
    def __init__(self):
        self.finished = []

    def finish_call_request(self, call_id):
        self.finished.append(call_id)
        return True


class FakeDB:
    def __init__(self):
        self.data = {}

    def get(self, owner, key, default=None):
        return self.data.get((owner, key), default)

    def set(self, owner, key, value):
        self.data[(owner, key)] = value


@pytest.fixture
def vk():
    return FakeVK()


@pytest.fixture
def db():
    return FakeDB()


RESP = {
    "call_id": "abc123",
    "join_link": "https://vk.com/call/abc123",
    "short_credentials": {"id": "12ab", "password": "pw1",
                          "link_with_password": "https://vk.cc/12ab"},
}


def test_add_and_get(vk):
    c = CallsCache(vk)
    e = c.add(RESP)
    assert e["call_id"] == "abc123"
    assert c.get("abc123") is e
    assert c.get("zzz") is None


def test_add_without_call_id_raises(vk):
    c = CallsCache(vk)
    with pytest.raises(ValueError):
        c.add({"join_link": "x"})


def test_persisted_to_db(vk, db):
    c = CallsCache(vk, db)
    c.add(RESP)
    assert db.get("vkover.calls", "active")["abc123"]["call_id"] == "abc123"


def test_remove(vk, db):
    c = CallsCache(vk, db)
    c.add(RESP)
    assert c.remove("abc123") is not None
    assert c.get("abc123") is None
    assert db.get("vkover.calls", "active") == {}


def test_finish_calls_api_and_removes(vk, db):
    c = CallsCache(vk, db)
    c.add(RESP)
    c.finish("abc123")
    assert vk.finished == ["abc123"]
    assert c.get("abc123") is None


def test_load_restores_from_db(vk, db):
    c1 = CallsCache(vk, db)
    c1.add(RESP)
    c2 = CallsCache(vk, db)
    c2.load()
    assert c2.get("abc123")["join_link"] == RESP["join_link"]


def test_all(vk):
    c = CallsCache(vk)
    c.add(RESP)
    c.add({**RESP, "call_id": "def456"})
    ids = {e["call_id"] for e in c.all()}
    assert ids == {"abc123", "def456"}
