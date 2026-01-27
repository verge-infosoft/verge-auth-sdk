from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
import httpx
import os
import asyncio
import jwt
from typing import List

from .secret_provider import get_secret
from .helpers import (
    get_external_url,
    get_cookie_domain,
    get_cookie_settings,
    post_with_retries,
)
from .verge_routes import router as verge_routes_router


# -------------------------------------------------------------------
# Globals
# -------------------------------------------------------------------

REGISTERED_ROUTES: List = []

JWT_PUBLIC_KEY: str | None = None
JWT_KEY_ID: str | None = None
JWT_ALGORITHMS = ["RS256"]


# -------------------------------------------------------------------
# Load JWT Public Key
# -------------------------------------------------------------------

async def load_public_key(force: bool = False):
    global JWT_PUBLIC_KEY, JWT_KEY_ID

    if JWT_PUBLIC_KEY and not force:
        return

    AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "").rstrip("/")
    AUTH_PUBLIC_KEY_URL = f"{AUTH_BASE_URL}/auth/keys/public"

    if not AUTH_PUBLIC_KEY_URL:
        raise RuntimeError("AUTH_PUBLIC_KEY_URL not configured")

    async with httpx.AsyncClient(timeout=50) as client:
        resp = await client.get(AUTH_PUBLIC_KEY_URL)
        resp.raise_for_status()
        data = resp.json()

        JWT_PUBLIC_KEY = data.get("public_key")
        JWT_KEY_ID = data.get("kid")

        if not JWT_PUBLIC_KEY:
            raise RuntimeError("Failed to load JWT public key")


# -------------------------------------------------------------------
# Main Entry
# -------------------------------------------------------------------

def add_central_auth(app: FastAPI):
    AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "").rstrip("/")
    SERVICE_NAME = os.getenv("SERVICE_NAME")
    SERVICE_BASE_URL = os.getenv("SERVICE_BASE_URL")

    CLIENT_ID = os.getenv("VERGE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("VERGE_CLIENT_SECRET")
    VERGE_SERVICE_SECRET = os.getenv("VERGE_SERVICE_SECRET")

    AUTH_REGISTER_URL = f"{AUTH_BASE_URL}/service-registry/register"
    AUTH_ROUTE_SYNC_URL = f"{AUTH_BASE_URL}/route-sync"
    INTROSPECT_URL = f"{AUTH_BASE_URL}/introspect"

    app.include_router(verge_routes_router)

    # ----------------------------------------------------------------
    # Startup: register service & routes
    # ----------------------------------------------------------------
    @app.on_event("startup")
    async def verge_bootstrap():
        await load_public_key(force=True)
        await asyncio.sleep(1)

        REGISTERED_ROUTES.clear()

        for route in app.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", [])

            if not path or path.startswith(("/docs", "/openapi", "/__verge__")):
                continue

            for method in methods:
                if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    REGISTERED_ROUTES.append(
                        {"path": path, "method": method}
                    )

        async with httpx.AsyncClient() as client:
            await post_with_retries(
                client,
                AUTH_REGISTER_URL,
                json={
                    "service_name": SERVICE_NAME,
                    "base_url": SERVICE_BASE_URL,
                },
                headers={
                    "X-Client-Id": CLIENT_ID or "",
                    "X-Client-Secret": CLIENT_SECRET or "",
                    "X-Verge-Service-Secret": VERGE_SERVICE_SECRET or "",
                },
            )

            await post_with_retries(
                client,
                AUTH_ROUTE_SYNC_URL,
                json={
                    "service_name": SERVICE_NAME,
                    "base_url": SERVICE_BASE_URL,
                    "routes": REGISTERED_ROUTES,
                },
                headers={
                    "X-Client-Id": CLIENT_ID or "",
                    "X-Client-Secret": CLIENT_SECRET or "",
                    "X-Verge-Service-Secret": VERGE_SERVICE_SECRET or "",
                },
                timeout=20,
            )

    # ----------------------------------------------------------------
    # Central Auth Middleware
    # ----------------------------------------------------------------
    @app.middleware("http")
    async def central_auth(request: Request, call_next):
        path = request.url.path
        normalized_path = path.rstrip("/")

        # ------------------------------------------------------------
        # Skip internal paths
        # ------------------------------------------------------------
        if normalized_path.startswith("/__verge__"):
            return await call_next(request)

        # ------------------------------------------------------------
        # Step 1 — Handle auth code callback
        # ------------------------------------------------------------
        code = request.query_params.get("code")
        if code:
            if request.cookies.get("verge_access"):
                return RedirectResponse(
                    str(request.url.remove_query_params("code")),
                    status_code=302,
                )

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{AUTH_BASE_URL}/auth/exchange",
                    json={"code": code},
                    headers={
                        "X-Client-Id": CLIENT_ID or "",
                        "X-Client-Secret": CLIENT_SECRET or "",
                    },
                )
                resp.raise_for_status()

                token = resp.json().get("access_token")
                if not token:
                    return JSONResponse(
                        {"detail": "Authorization failed"},
                        status_code=401,
                    )

                response = RedirectResponse(
                    str(request.url.remove_query_params("code")),
                    status_code=302,
                )
                response.set_cookie(
                    key="verge_access",
                    value=token,
                    **get_cookie_settings(request),
                )
                return response

        # ------------------------------------------------------------
        # Step 2 — Extract token
        # ------------------------------------------------------------
        token = request.cookies.get("verge_access")

        if not token:
            auth = request.headers.get("authorization")
            if auth and auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1]

        PUBLIC_PATHS = {
            "/" + p.strip("/ ")
            for p in os.getenv("PUBLIC_PATHS", "").split(",")
            if p.strip()
        }

        if not token:
            if normalized_path in PUBLIC_PATHS:
                return await call_next(request)

            login_url = (
                f"{os.getenv('AUTH_LOGIN_URL')}?"
                f"redirect_url={get_external_url(request)}"
            )
            return RedirectResponse(login_url, status_code=302)

        # ------------------------------------------------------------
        # Step 3 — Verify JWT
        # ------------------------------------------------------------
        try:
            payload = jwt.decode(
                token,
                JWT_PUBLIC_KEY,
                algorithms=JWT_ALGORITHMS,
                options={"require": ["exp", "iat"]},
            )
        except jwt.ExpiredSignatureError:
            response = RedirectResponse(
                f"{os.getenv('AUTH_LOGIN_URL')}?"
                f"redirect_url={request.url}&reason=expired",
                status_code=302,
            )
            response.delete_cookie("verge_access")
            return response

        except jwt.InvalidTokenError:
            response = RedirectResponse(
                f"{os.getenv('AUTH_LOGIN_URL')}?"
                f"redirect_url={request.url}&reason=invalid",
                status_code=302,
            )
            response.delete_cookie("verge_access")
            return response

        # # ------------------------------------------------------------
        # # Step 4 — Introspect (optional)
        # # ------------------------------------------------------------
        # if INTROSPECT_URL:
        #     async with httpx.AsyncClient(timeout=5) as client:
        #         resp = await client.post(
        #             INTROSPECT_URL,
        #             headers={
        #                 "Authorization": f"Bearer {token}",
        #                 "X-Client-Id": CLIENT_ID or "",
        #                 "X-Client-Secret": CLIENT_SECRET or "",
        #             },
        #         )
        #         if resp.status_code != 200:
        #             return RedirectResponse(
        #                 os.getenv("AUTH_LOGIN_URL"),
        #                 status_code=302,
        #             )

        # ------------------------------------------------------------
        # Step 5 — Authorization check
        # ------------------------------------------------------------
        permissions = payload.get("roles", [])
        route_path = normalized_path or "/"
        method = request.method.upper()

        required_key = f"{SERVICE_NAME}:{route_path}:{method}".lower()
        if required_key not in [p.lower() for p in permissions]:
            return JSONResponse(
                {
                    "detail": "Insufficient permissions",
                    "required": required_key,
                },
                status_code=403,
            )

        request.state.user = payload
        return await call_next(request)

