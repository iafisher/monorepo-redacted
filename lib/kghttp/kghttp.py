import random
import time
from typing import Literal, Self

import requests

from iafisher_foundation.prelude import *


class KgHttpError(KgError):
    pass


BackoffStrategy = Literal["linear", "exponential"]

JITTER_PERCENT = 0.25
EXPONENTIAL_BACKOFF_FACTOR = 2
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_AFTER = datetime.timedelta(seconds=5)
DEFAULT_MAX_SLEEP = datetime.timedelta(seconds=300)
DEFAULT_TIMEOUT_SECS = 30.0


@dataclass
class RetryConfig:
    # `max_retries` does not include the initial request. So if `max_retries=2`, the HTTP
    # request will be made up to 3 times.
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_after: datetime.timedelta = DEFAULT_RETRY_AFTER
    # If `linear`, then sleep for `retry_after` after every failure.
    # If `exponential`, then double the previous sleep time after every failure.
    backoff_strategy: BackoffStrategy = "linear"
    # Sleep time is capped at `max_sleep` even if backoff strategy would otherwise result in
    # a longer sleep. (Prevents exponential backoff from sleeping for hours.)
    max_sleep: datetime.timedelta = datetime.timedelta(seconds=300)
    # If `random_jitter` is true, then add/subtract a random amount of sleep time capped at
    # `JITTER_PERCENT`.
    random_jitter: bool = True
    # If `switch_to_exponential_if_http_429` is true, then change backoff strategy to
    # 'exponential' for all subsequent requests.
    switch_to_exponential_if_http_429: bool = True

    @classmethod
    def exponential(
        cls,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_after: datetime.timedelta = DEFAULT_RETRY_AFTER,
        max_sleep: datetime.timedelta = DEFAULT_MAX_SLEEP,
    ) -> Self:
        return cls(
            max_retries=max_retries,
            retry_after=retry_after,
            backoff_strategy="exponential",
            max_sleep=max_sleep,
        )

    def validate(self) -> None:
        fld = lambda s: f"`RetryConfig.{s}`"
        if self.max_retries <= 0:
            raise KgError(
                f"{fld('max_retries')} must be a positive integer",
                max_retries=self.max_retries,
            )

        if self.retry_after > self.max_sleep:
            raise KgError(
                f"{fld('retry_after')} cannot be larger than {fld('max_sleep')}",
                retry_after=self.retry_after,
                max_sleep=self.max_sleep,
            )

        if (
            self.backoff_strategy == "exponential"
            and self.retry_after * EXPONENTIAL_BACKOFF_FACTOR > self.max_sleep
        ):
            raise KgError(
                f"{fld('retry_after')} times the exponential backoff factor is greater than {fld('max_sleep')}"
                "; this effectively disables exponential backoff",
                retry_after=self.retry_after,
                max_sleep=self.max_sleep,
                factor=EXPONENTIAL_BACKOFF_FACTOR,
            )


def get(
    url: str,
    *,
    timeout_secs: Union[Optional[float], Nothing] = NOTHING,
    retry_config: Union[Optional[RetryConfig], Nothing] = NOTHING,
    headers: Optional[Dict[str, str]] = None,
    raise_on_error: bool = True,
    allow_redirects: bool = True,
) -> requests.Response:
    """
    Perform an HTTP GET request.

    If not specified, defaults to reasonable time-out and retry logic.
    """
    return _request(
        "GET",
        url,
        timeout_secs=timeout_secs,
        retry_config=retry_config,
        headers=headers,
        raise_on_error=raise_on_error,
        allow_redirects=allow_redirects,
    )


def post(
    url: str,
    *,
    data: Any = None,
    json: Any = None,
    timeout_secs: Union[Optional[float], Nothing] = NOTHING,
    retry_config: Union[Optional[RetryConfig], Nothing] = NOTHING,
    headers: Optional[Dict[str, str]] = None,
    raise_on_error: bool = True,
    allow_redirects: bool = True,
) -> requests.Response:
    """
    Perform an HTTP POST request.

    If not specified, defaults to reasonable time-out and retry logic.
    """
    return _request(
        "POST",
        url,
        data=data,
        json=json,
        timeout_secs=timeout_secs,
        retry_config=retry_config,
        headers=headers,
        raise_on_error=raise_on_error,
        allow_redirects=allow_redirects,
    )


def _request(
    verb: str,
    url: str,
    *,
    data: Any = None,
    json: Any = None,
    timeout_secs: Union[Optional[float], Nothing] = NOTHING,
    retry_config: Union[Optional[RetryConfig], Nothing] = NOTHING,
    sleep_impl: Optional[Callable[[float], None]] = None,
    random_uniform_impl: Optional[Callable[[float, float], float]] = None,
    headers: Optional[Dict[str, str]] = None,
    raise_on_error: bool = True,
    allow_redirects: bool = True,
) -> requests.Response:
    if isinstance(retry_config, Nothing):
        retry_config = RetryConfig()
    elif retry_config is not None:
        retry_config.validate()

    if isinstance(timeout_secs, Nothing):
        timeout_secs = DEFAULT_TIMEOUT_SECS

    retry_state = RetryState.from_config(retry_config, random_uniform_impl)
    while True:
        retry_state.attempts_so_far += 1
        LOG.info(
            "sending HTTP %s request to %s (attempt %s of %s)",
            verb,
            url,
            retry_state.attempts_so_far,
            retry_state.max_attempts(),
        )

        response = None
        try:
            response = requests.request(
                verb,
                url,
                data=data,
                json=json,
                timeout=timeout_secs,
                headers=headers,
                allow_redirects=allow_redirects,
            )
        except requests.ConnectionError:
            LOG.warning(
                "HTTP %s request failed with connection error (url: %s)", verb, url
            )
        except requests.exceptions.Timeout:
            LOG.warning(
                "HTTP %s request timed out after %s second(s) (url: %s)",
                verb,
                timeout_secs,
                url,
            )
        else:
            if 200 <= response.status_code < 400:
                LOG.info(
                    "HTTP %s request succeeded with status code %s (%s byte(s), url: %s)",
                    verb,
                    response.status_code,
                    len(response.content),
                    url,
                )
                return response
            elif response.status_code == 408:
                LOG.warning(
                    "HTTP %s request failed with status code 408 Request Timeout (url: %s)",
                    verb,
                    url,
                )
            elif response.status_code == 429:
                LOG.warning(
                    "HTTP %s request failed with status code 429 Too Many Requests (url: %s)",
                    verb,
                    url,
                )
            elif 400 <= response.status_code < 500:
                if raise_on_error:
                    raise KgHttpError(
                        "HTTP request failed with status code 4xx",
                        verb=verb,
                        url=url,
                        status_code=response.status_code,
                        response_text=response.text,
                    )
                else:
                    return response
            elif 500 <= response.status_code < 600:
                LOG.warning(
                    "HTTP %s request failed with status code %s (url: %s)",
                    verb,
                    response.status_code,
                    url,
                )
            else:
                LOG.warning(
                    "HTTP %s request returned unexpected status code %s (url: %s)",
                    verb,
                    response.status_code,
                    url,
                )

        retry_result = retry_state.tick(
            response.status_code if response is not None else None
        )
        match retry_result:
            case DoNotRetry():
                if raise_on_error or response is None:
                    max_attempts = retry_state.max_attempts()
                    message = (
                        "HTTP request failed too many times"
                        if max_attempts > 1
                        else "HTTP request failed"
                    )
                    raise KgHttpError(
                        message,
                        verb=verb,
                        url=url,
                        max_attempts=retry_state.max_attempts(),
                        last_response=response,
                    )
                else:
                    return response
            case RetryAfter(seconds):
                LOG.info(
                    "sleeping for %.1fs before retrying HTTP %s request (url: %s)",
                    seconds,
                    verb,
                    url,
                )
                (sleep_impl or time.sleep)(seconds)


@dataclass
class RetryAfter:
    seconds: float


@dataclass
class DoNotRetry:
    pass


RetryResult = Union[RetryAfter, DoNotRetry]


@dataclass(slots=True)
class RetryState:
    config: Optional[RetryConfig]
    backoff_strategy: Optional[BackoffStrategy]
    attempts_so_far: int
    last_sleep_secs: Optional[float]
    random_uniform_impl: Optional[Callable[[float, float], float]]

    @classmethod
    def from_config(
        cls,
        config: Optional[RetryConfig],
        random_uniform_impl: Optional[Callable[[float, float], float]] = None,
    ) -> Self:
        if config is None:
            return cls(None, None, 0, None, random_uniform_impl)
        else:
            return cls(config, config.backoff_strategy, 0, None, random_uniform_impl)

    def tick(self, status_code: Optional[int]) -> RetryResult:
        if self.config is None or self.attempts_so_far >= self.config.max_retries + 1:
            return DoNotRetry()

        if status_code == 429 and self.config.switch_to_exponential_if_http_429:
            self.backoff_strategy = "exponential"

        max_sleep_secs = self.config.max_sleep.total_seconds()
        match self.backoff_strategy:
            case "exponential":
                if self.last_sleep_secs is not None:
                    base_sleep_secs = min(
                        self.last_sleep_secs * EXPONENTIAL_BACKOFF_FACTOR,
                        max_sleep_secs,
                    )
                else:
                    base_sleep_secs = self.config.retry_after.total_seconds()
            case "linear":
                base_sleep_secs = self.config.retry_after.total_seconds()
            case None:
                impossible()

        # save `last_sleep_secs` before adding jitter
        self.last_sleep_secs = base_sleep_secs
        total_sleep_secs = min(
            self._jitter(self.config, base_sleep_secs), max_sleep_secs
        )
        return RetryAfter(total_sleep_secs)

    def max_attempts(self) -> int:
        return self.config.max_retries + 1 if self.config is not None else 1

    def _jitter(self, config: RetryConfig, base_secs: float) -> float:
        if config.random_jitter:
            return base_secs + max(
                0,
                (self.random_uniform_impl or random.uniform)(
                    base_secs * -JITTER_PERCENT, base_secs * JITTER_PERCENT
                ),
            )
        else:
            return base_secs
