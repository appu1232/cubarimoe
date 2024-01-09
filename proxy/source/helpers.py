import base64

import requests
from django.core.cache import cache
from django.conf import settings
from urllib.parse import urlparse
from .data import ProxyException

ENCODE_STR_SLASH = "%FF-"
ENCODE_STR_QUESTION = "%DE-"
GLOBAL_HEADERS = {
    "User-Agent": "Mozilla Firefox Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:53.0) Gecko/20100101 Firefox/53.0.",
    "x-requested-with": "cubari",
}
PROXY = "https://cubari-cors.herokuapp.com/"

REQUEST_TIMEOUT = 8
SENSOR_TIMEOUT_PREFIX = "timeout_sensor/"
SENSOR_TIMEOUT_TTL = 10 * 60      # 10 minute timeout on automatic suspension.
SENSOR_TIMEOUT_MAX_FAILURES = 25  # 25 requests within 5 minutes time out? Drop the proxy.



def naive_encode(url):
    return url.replace("/", ENCODE_STR_SLASH).replace("?", ENCODE_STR_QUESTION)


def naive_decode(url):
    return url.replace(ENCODE_STR_SLASH, "/").replace(ENCODE_STR_QUESTION, "?")


def decode(url: str):
    """Base64 URL decoding wrapper that automatically pads the string."""
    padding: int = 4 - (len(url) % 4)
    return str(base64.urlsafe_b64decode((url + ("=" * padding)).encode()), "utf-8")


def encode(url: str):
    """Base64 URL encoding wrapper that automatically strips the = symbols, ensuring URL safety."""
    return str(base64.urlsafe_b64encode(url.encode()), "utf-8").rstrip("=")


def sensored_request_handler(req_handler, original_url):
    original_hostname = urlparse(original_url).hostname
    sensor_cache_key = f"{SENSOR_TIMEOUT_PREFIX}{original_hostname}"

    if cache.get(sensor_cache_key, 0) > SENSOR_TIMEOUT_MAX_FAILURES:
        raise ProxyException(f"This proxy has temporarily been disabled due to service degradation. Please try again in {SENSOR_TIMEOUT_TTL / 60} minutes.")

    try:
        return req_handler()
    except requests.exceptions.Timeout:
        # This isn't atomic, but rather a "best-effort" guard on the number of failures
        cache.set(sensor_cache_key, cache.get(sensor_cache_key, 0) + 1, SENSOR_TIMEOUT_TTL)
        raise ProxyException("Downstream server timed out. Please try again.")

def get_wrapper(url, *, headers={}, use_proxy=False, **kwargs):
    request_url = (
        f"{settings.EXTERNAL_PROXY_URL}/v1/cors/{encode(url)}?source=cubari_host"
        if use_proxy
        else url
    )
    return sensored_request_handler(lambda: requests.get(request_url, headers={**GLOBAL_HEADERS, **headers}, timeout=REQUEST_TIMEOUT, **kwargs), url)


def post_wrapper(url, headers={}, use_proxy=False, **kwargs):
    request_url = (
        f"{settings.EXTERNAL_PROXY_URL}/v1/cors/{encode(url)}?source=cubari_host"
        if use_proxy
        else url
    )
    return sensored_request_handler(lambda: requests.post(request_url, headers={**GLOBAL_HEADERS, **headers}, timeout=REQUEST_TIMEOUT, **kwargs), url)


def api_cache(*, prefix, time):
    def wrapper(f):
        def inner(self, meta_id):
            data = cache.get(f"{prefix}_{meta_id}")
            if not data:
                data = f(self, meta_id)
                if not data:
                    return None
                else:
                    cache.set(f"{prefix}_{meta_id}", data, time)
                    return data
            else:
                return data

        return inner

    return wrapper
