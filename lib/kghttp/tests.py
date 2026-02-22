import http.server
import json
import logging
import socket
import threading
import time
from typing import Self

import requests

from iafisher_foundation.prelude import *
from lib.testing import *

from .kghttp import KgHttpError, RetryConfig, _request


def random_uniform_impl_zero(low: float, high: float) -> float:
    assert low <= 0 <= high
    return 0


def random_uniform_impl_max(_low: float, high: float) -> float:
    return high


@dataclass
class TestBehavior:
    status_code: int
    succeed_after: Optional[int] = None
    sleep_seconds: Optional[float] = None

    def next_status_code(self) -> int:
        if self.succeed_after is not None:
            if self.succeed_after == 0:
                return 200
            else:
                self.succeed_after -= 1
                return self.status_code
        else:
            return self.status_code


# TODO(2026-01): Run a single server for all tests, hit endpoints like /http-200 to trigger
# particular status codes.
#
# One tricky part: 'succeed after N tries' semantics


class TestRequestHandler(http.server.BaseHTTPRequestHandler):
    @override
    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default logging from BaseHTTPRequestHandler
        pass

    def do_GET(self) -> None:
        self._handle_request()

    def do_POST(self) -> None:
        self._handle_request()

    def _handle_request(self) -> None:
        behavior = getattr(self.server, "test_behavior", None)
        if behavior is None:
            self.send_error(500, "No test behavior configured")
            return

        if not isinstance(behavior, TestBehavior):
            self.send_error(500, "Test behavior is not an instance of TestBehavior")
            return

        status_code = behavior.next_status_code()
        if behavior.sleep_seconds is not None:
            time.sleep(behavior.sleep_seconds)

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        body = json.dumps({"success": status_code == 200}).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError):
            # If sleeping, we expect errors from the client timing out.
            if behavior.sleep_seconds is None:
                raise


class BrokenRequestHandler(http.server.BaseHTTPRequestHandler):
    @override
    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default logging from BaseHTTPRequestHandler
        pass

    def do_GET(self) -> None:
        pass

    def do_POST(self) -> None:
        pass


class TestHTTPServer:
    def __init__(
        self, behavior: TestBehavior, handler_cls: Any = TestRequestHandler
    ) -> None:
        self.behavior = behavior
        self.server = None
        self.thread = None
        self.port = None
        self.handler_cls = handler_cls

    def start(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]

        self.server = http.server.HTTPServer(("127.0.0.1", self.port), self.handler_cls)
        self.server.test_behavior = self.behavior  # type: ignore

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        # Give the server a moment to start
        time.sleep(0.01)

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1.0)

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class Test(BaseExpectStdout):
    @override
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        logging.disable()

    def test_successful_request(self) -> None:
        with TestHTTPServer(TestBehavior(200)) as server:
            self.do_post(server)
            self.assertExpectedInline(self.stdout(), """""")

    def test_timeout(self):
        # TODO(2026-01): Spawn request handlers in their own threads so that `sleep_seconds`
        # doesn't happen on the main thread. (`server.stop()` waits for all request handlers
        # to finish.)
        with TestHTTPServer(TestBehavior(200, sleep_seconds=0.5)) as server:
            with self.assertRaisesRegex(KgHttpError, "failed too many times"):
                self.do_get(
                    server,
                    retry_config=RetryConfig(
                        max_retries=1, retry_after=datetime.timedelta(seconds=0.01)
                    ),
                )
            self.assertExpectedInline(
                self.stdout(),
                """\
test: sleep for 0.0s
""",
            )

    def test_jitter(self) -> None:
        with TestHTTPServer(TestBehavior(500, succeed_after=2)) as server:
            self.do_post(server, random_uniform_impl=random_uniform_impl_max)
            self.assertExpectedInline(
                self.stdout(),
                """\
test: sleep for 6.2s
test: sleep for 6.2s
""",
            )

    def test_exponential_backoff(self) -> None:
        with TestHTTPServer(TestBehavior(500, succeed_after=2)) as server:
            self.do_post(server, retry_config=RetryConfig.exponential())
            self.assertExpectedInline(
                self.stdout(),
                """\
test: sleep for 5.0s
test: sleep for 10.0s
""",
            )

    def test_exponential_backoff_with_jitter(self) -> None:
        with TestHTTPServer(TestBehavior(500, succeed_after=2)) as server:
            self.do_post(
                server,
                retry_config=RetryConfig.exponential(),
                random_uniform_impl=random_uniform_impl_max,
            )
            self.assertExpectedInline(
                self.stdout(),
                """\
test: sleep for 6.2s
test: sleep for 12.5s
""",
            )

    def test_exponential_backoff_with_cap(self) -> None:
        with TestHTTPServer(TestBehavior(500)) as server:
            with self.assertRaisesRegex(KgHttpError, "failed too many times"):
                self.do_post(
                    server,
                    retry_config=RetryConfig.exponential(
                        max_retries=7, max_sleep=datetime.timedelta(seconds=60)
                    ),
                )
            self.assertExpectedInline(
                self.stdout(),
                """\
test: sleep for 5.0s
test: sleep for 10.0s
test: sleep for 20.0s
test: sleep for 40.0s
test: sleep for 60.0s
test: sleep for 60.0s
test: sleep for 60.0s
""",
            )

    def test_http_4xx(self) -> None:
        with TestHTTPServer(TestBehavior(400)) as server:
            with self.assertRaisesRegex(KgHttpError, "status code 4xx"):
                self.do_post(server)
            self.assertExpectedInline(self.stdout(), """""")

    def test_http_429(self) -> None:
        with TestHTTPServer(TestBehavior(429)) as server:
            with self.assertRaisesRegex(KgHttpError, "failed too many times"):
                self.do_post(server)

            # HTTP 429 should result in exponential backoff
            self.assertExpectedInline(
                self.stdout(),
                """\
test: sleep for 5.0s
test: sleep for 10.0s
""",
            )

    def test_no_retries(self) -> None:
        with TestHTTPServer(TestBehavior(500)) as server:
            with self.assertRaisesRegex(KgHttpError, "HTTP request failed"):
                self.do_post(server, retry_config=None)
            self.assertExpectedInline(self.stdout(), """""")

    def test_connection_error(self) -> None:
        with TestHTTPServer(TestBehavior(200), BrokenRequestHandler) as server:
            with self.assertRaisesRegex(KgHttpError, "HTTP request failed"):
                self.do_get(server, retry_config=None)
        self.assertExpectedInline(self.stdout(), """""")

    def do_get(
        self,
        server: TestHTTPServer,
        retry_config: Union[Optional[RetryConfig], Nothing] = NOTHING,
        random_uniform_impl: Any = random_uniform_impl_zero,
    ) -> requests.Response:
        url = server.url()
        return _request(
            "GET",
            url,
            timeout_secs=0.5,
            sleep_impl=sleep_impl,
            random_uniform_impl=random_uniform_impl,
            retry_config=retry_config,
        )

    def do_post(
        self,
        server: TestHTTPServer,
        retry_config: Union[Optional[RetryConfig], Nothing] = NOTHING,
        random_uniform_impl: Any = random_uniform_impl_zero,
    ) -> requests.Response:
        url = server.url()
        return _request(
            "POST",
            url,
            timeout_secs=0.5,
            sleep_impl=sleep_impl,
            random_uniform_impl=random_uniform_impl,
            retry_config=retry_config,
        )


class SucceedAfter:
    def __init__(self, failure_result: Callable[[], Optional[int]], *, n: int) -> None:
        self._failure_result = failure_result
        self._failures = 0
        self._succeed_after = n
        self._lock = threading.Lock()

    def do(self, *args: Any, **kwargs: Any) -> Optional[int]:
        with self._lock:
            if self._failures < self._succeed_after:
                self._failures += 1
                return self._failure_result()
            else:
                return 200


def sleep_impl(seconds: float) -> None:
    print(f"test: sleep for {seconds:.1f}s")


def mock_timeout() -> int:
    raise requests.exceptions.Timeout()
