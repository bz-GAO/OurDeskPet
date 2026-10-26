"""Bounded retries for rejected requests and safe read operations."""
import time
from urllib.error import HTTPError, URLError


def request_with_retry(operation, *, safe_read=False, sleep=time.sleep, on_retry=None):
    """Retry explicit rate-limit rejection long enough for a provider window to reset.

    POST transport failures remain single-shot because the provider may already have
    accepted and charged an ambiguous request. HTTP 429 is safe to retry: the server
    explicitly rejected it before inference.
    """
    delays = (10, 20, 40, 60, 60)
    for attempt in range(len(delays) + 1):
        try:
            return operation()
        except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
            # An ambiguous POST timeout may already have incurred a charge.
            retryable = (isinstance(error, HTTPError) and error.code == 429) or (
                safe_read and (not isinstance(error, HTTPError) or error.code in {408, 429, 500, 502, 503, 504}))
            if not retryable or attempt == len(delays):
                raise
            delay = delays[attempt]
            if isinstance(error, HTTPError):
                try:
                    delay = min(120, max(delay, float(error.headers.get('Retry-After', delay))))
                except (ValueError, AttributeError):
                    pass
            if on_retry is not None:
                on_retry(attempt + 1, delay, error)
            sleep(delay)
