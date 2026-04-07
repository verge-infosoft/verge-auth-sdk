from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from .secret_provider import get_secret
import httpx
import os

router = APIRouter()


@router.get("/__verge__/routes", include_in_schema=False)
async def verge_internal_routes(request: Request):

    expected_secret = get_secret("VERGE_SERVICE_SECRET")
    received_secret = request.headers.get("X-Verge-Service-Secret")

    if not expected_secret or expected_secret != received_secret:

        raise HTTPException(status_code=403, detail="Forbidden")

    collected = []

    INTERNAL_PREFIXES = (
        "/__verge__",
        "/api/auth/",
    )

    for route in request.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", [])

        if not path:
            continue

        if path.startswith(INTERNAL_PREFIXES):
            continue

        for method in methods:
            if method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                collected.append({
                    "path": path,
                    "method": method
                })

    collected.sort(key=lambda r: (r["path"], r["method"]))

    return collected


@router.post("/api/auth/exchange", include_in_schema=False)
async def verge_exchange_code(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    code = body.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "").rstrip("/")
    CLIENT_ID = os.getenv("VERGE_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("VERGE_CLIENT_SECRET", "")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{AUTH_BASE_URL}/auth/exchange",
            json={"code": code},
            headers={
                "X-Client-Id": CLIENT_ID,
                "X-Client-Secret": CLIENT_SECRET,
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Code exchange failed")

        token = resp.json().get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="No token returned")

    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        key="verge_access",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response
