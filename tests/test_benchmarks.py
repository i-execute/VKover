import pytest

from vkover.client import Client
from vkover.handlers import wrap
from vkover.models import Message


@pytest.fixture
def client():
    c = Client("tok", delay=0)
    c._http = FakeHTTP()
    return c


class FakeHTTP:
    def post(self, url, data=None):
        class R:
            @staticmethod
            def json():
                return {"response": 1}
        return R()


def test_bench_call(benchmark, client):
    benchmark(lambda: client.call("messages.send", peer_id=1, message="x"))


RAW = [4, 6692, 33, 100, 1791440048, "сообщение текст", {"title": " ... "}, {}]


def test_bench_wrap(benchmark):
    benchmark(lambda: wrap(RAW))


def test_bench_parse(benchmark):
    d = {"id": 1, "peer_id": 100, "from_id": 200, "date": 123, "text": "hello"}
    benchmark(lambda: Message.from_api(d))
