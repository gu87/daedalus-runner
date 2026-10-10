import io
import json
import unittest
from unittest import mock
from urllib import error as urllib_error

from tools.delegate_runtime.backend import DaedalusBackend


class _FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._raw


class _FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def urlopen(self, req, timeout=None):
        self.calls += 1
        if not self.responses:
            raise AssertionError("no more mocked responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item)


def _http_error(code):
    return urllib_error.HTTPError("http://127.0.0.1:7878", code, "boom", {}, io.BytesIO(b""))


class TestDaedalusBackendRetry(unittest.TestCase):
    def _make_backend(self, responses, max_retries=3, retry_delay=1.0):
        opener = _FakeOpener(responses)
        backend = DaedalusBackend(
            "http://127.0.0.1:7878",
            opener=opener,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        return backend, opener

    def test_success_first_try(self):
        backend, opener = self._make_backend([{"ok": True}])
        self.assertEqual(backend._request("GET", "/x"), {"ok": True})
        self.assertEqual(opener.calls, 1)

    def test_retries_on_500_then_succeeds(self):
        backend, opener = self._make_backend([_http_error(500), {"ok": True}])
        with mock.patch("tools.delegate_runtime.backend.time.sleep"):
            self.assertEqual(backend._request("GET", "/x"), {"ok": True})
        self.assertEqual(opener.calls, 2)

    def test_retries_on_429_then_succeeds(self):
        backend, opener = self._make_backend([_http_error(429), {"ok": True}])
        with mock.patch("tools.delegate_runtime.backend.time.sleep"):
            self.assertEqual(backend._request("GET", "/x"), {"ok": True})
        self.assertEqual(opener.calls, 2)

    def test_does_not_retry_404(self):
        backend, opener = self._make_backend([_http_error(404)])
        with self.assertRaises(urllib_error.HTTPError):
            backend._request("GET", "/missing")
        self.assertEqual(opener.calls, 1)

    def test_does_not_retry_400(self):
        backend, opener = self._make_backend([_http_error(400)])
        with self.assertRaises(urllib_error.HTTPError):
            backend._request("POST", "/api/tasks")
        self.assertEqual(opener.calls, 1)

    def test_retries_connection_error_then_succeeds(self):
        backend, opener = self._make_backend(
            [urllib_error.URLError(ConnectionRefusedError("refused")), {"ok": True}]
        )
        with mock.patch("tools.delegate_runtime.backend.time.sleep"):
            self.assertEqual(backend._request("GET", "/x"), {"ok": True})
        self.assertEqual(opener.calls, 2)

    def test_retries_timeout_then_succeeds(self):
        backend, opener = self._make_backend(
            [urllib_error.URLError(TimeoutError("timed out")), {"ok": True}]
        )
        with mock.patch("tools.delegate_runtime.backend.time.sleep"):
            self.assertEqual(backend._request("GET", "/x"), {"ok": True})
        self.assertEqual(opener.calls, 2)

    def test_retries_direct_timeout_then_succeeds(self):
        backend, opener = self._make_backend([TimeoutError("timed out"), {"ok": True}])
        with mock.patch("tools.delegate_runtime.backend.time.sleep"):
            self.assertEqual(backend._request("GET", "/x"), {"ok": True})
        self.assertEqual(opener.calls, 2)

    def test_exhausts_retries_on_500(self):
        backend, opener = self._make_backend([_http_error(500)] * 10, max_retries=3)
        with mock.patch("tools.delegate_runtime.backend.time.sleep"):
            with self.assertRaises(urllib_error.HTTPError):
                backend._request("GET", "/x")
        self.assertEqual(opener.calls, 4)

    def test_exponential_backoff_delays(self):
        backend, opener = self._make_backend([_http_error(500)] * 10, max_retries=3)
        with mock.patch("tools.delegate_runtime.backend.time.sleep") as sleep:
            with self.assertRaises(urllib_error.HTTPError):
                backend._request("GET", "/x")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1.0, 2.0, 4.0])

    def test_respects_custom_retry_settings(self):
        backend, opener = self._make_backend(
            [_http_error(500)] * 10, max_retries=1, retry_delay=0.25
        )
        with mock.patch("tools.delegate_runtime.backend.time.sleep") as sleep:
            with self.assertRaises(urllib_error.HTTPError):
                backend._request("GET", "/x")
        self.assertEqual(opener.calls, 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.25])


if __name__ == "__main__":
    unittest.main()
