from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.sources.shared.common import make_session


class _RetryHandler(BaseHTTPRequestHandler):
    get_calls = 0
    post_calls = 0
    bad_request_calls = 0

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        type(self).get_calls += 1
        if type(self).get_calls == 1:
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_POST(self):  # noqa: N802
        if self.path == "/bad-request":
            type(self).bad_request_calls += 1
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        type(self).post_calls += 1
        if type(self).post_calls == 1:
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")


class RetryBackoffStage411Tests(unittest.TestCase):
    def setUp(self):
        _RetryHandler.get_calls = 0
        _RetryHandler.post_calls = 0
        _RetryHandler.bad_request_calls = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RetryHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_policy_covers_get_and_idempotent_collector_post(self):
        retry = make_session().get_adapter("http://").max_retries
        self.assertEqual(retry.allowed_methods, frozenset({"GET", "POST"}))
        self.assertTrue(retry.respect_retry_after_header)
        self.assertEqual(set(retry.status_forcelist), {429, 500, 502, 503, 504})

    def test_get_503_is_retried(self):
        response = make_session(retries=1, backoff=0).get(self.base + "/get", timeout=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_RetryHandler.get_calls, 2)

    def test_post_429_with_retry_after_is_retried(self):
        response = make_session(retries=1, backoff=0).post(self.base + "/search", data={"q": "research"}, timeout=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_RetryHandler.post_calls, 2)

    def test_non_retryable_400_is_not_retried(self):
        response = make_session(retries=2, backoff=0).post(self.base + "/bad-request", timeout=2)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_RetryHandler.bad_request_calls, 1)

    def test_retry_budget_and_backoff_remain_bounded(self):
        retry = make_session(retries=2, backoff=0.6).get_adapter("https://").max_retries
        self.assertEqual(retry.total, 2)
        self.assertEqual(retry.connect, 2)
        self.assertEqual(retry.read, 2)
        self.assertEqual(retry.status, 2)
        self.assertEqual(retry.backoff_factor, 0.6)


if __name__ == "__main__":
    unittest.main()
