from fastapi import FastAPI, Request
from urllib.parse import urlparse
import os
import asyncio


def is_request_secure(request: Request) -> bool:

    if request.url.scheme == "https":
        return True

    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto and forwarded_proto.lower() == "https":
        return True

    return False


def get_external_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host"))
    return f"{proto}://{host}{request.url.path}"


def get_cookie_domain():
    base = os.getenv("SERVICE_BASE_URL")
    if not base:
        return None

    host = urlparse(base).hostname
    if not host:
        return None

    if host.replace(".", "").isdigit():
        return None

    if host in ("localhost", "127.0.0.1"):
        return None

    parts = host.split(".")
    if len(parts) >= 2:
        return "." + ".".join(parts[-2:])

    return None


def get_cookie_settings(request: Request):
    return {
        "httponly": True,
        "secure": True,
        "samesite": "none",
        "path": "/",
        "domain": get_cookie_domain(),
        "max_age": 28800,
    }


async def post_with_retries(
    client,
    url,
    json=None,
    headers=None,
    timeout=10,
    retries=8,
    backoff=1,
):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = await client.post(
                url,
                json=json,
                headers=headers,
                timeout=timeout,
            )
            return resp
        except Exception as e:
            last_exc = e
            await asyncio.sleep(backoff * attempt)
    raise last_exc
