from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
import httpx
import os
import asyncio
import jwt
from typing import List
from urllib.parse import quote
from .secret_provider import get_secret
from .verge_routes import router as verge_routes_router

REGISTERED_ROUTES: List = []

# ============================================================
# GLOBAL JWT CACHE
# ============================================================
JWT_PUBLIC_KEY: str | None = None
JWT_KEY_ID: str | None = None
JWT_ALGORITHMS = ["RS256"]


# -----------------------------------------------------------
# HTTP helper with retries
# -----------------------------------------------------------
async def _post_with_retries(
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
            print(
                f"❗ Retry {attempt}/{retries} failed for {url}: "
                f"{type(e).__name__}: {e}"
            )
            await asyncio.sleep(backoff * attempt)
    raise last_exc


# -----------------------------------------------------------
# PUBLIC KEY DISCOVERY
# -----------------------------------------------------------
async def load_public_key(force: bool = False):
    """
    Loads and caches the JWT public key from auth-service.
    Safe to call multiple times.
    """
    global JWT_PUBLIC_KEY, JWT_KEY_ID

    if JWT_PUBLIC_KEY and not force:
        return

    AUTH_PUBLIC_KEY_URL = os.getenv("AUTH_PUBLIC_KEY_URL")
    if not AUTH_PUBLIC_KEY_URL:
        print("❌ AUTH_PUBLIC_KEY_URL not set! Please Set it.")
        return

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(AUTH_PUBLIC_KEY_URL)
            resp.raise_for_status()
            data = resp.json()

            JWT_PUBLIC_KEY = data.get("public_key")
            JWT_KEY_ID = data.get("kid")

            if JWT_PUBLIC_KEY:
                print("✅ Security Key Loaded Successfully")
            else:
                print("❌ Security Key Loading Failed")

    except Exception as e:
        print("❌ Failed to load Security Key:", str(e))


# -----------------------------------------------------------
# MAIN INTEGRATION
# -----------------------------------------------------------
def add_central_auth(app: FastAPI):

    AUTH_LOGIN_URL = os.getenv("AUTH_LOGIN_URL")

    SERVICE_NAME = os.getenv("SERVICE_NAME")
    SERVICE_BASE_URL = os.getenv("SERVICE_BASE_URL")

    CLIENT_ID = os.getenv("VERGE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("VERGE_CLIENT_SECRET")

    VERGE_SERVICE_SECRET = get_secret("VERGE_SERVICE_SECRET")

    AUTH_REGISTER_URL = os.getenv("AUTH_REGISTER_URL")
    AUTH_ROUTE_SYNC_URL = os.getenv("AUTH_ROUTE_SYNC_URL")
    INTROSPECT_URL = os.getenv("AUTH_INTROSPECT_URL")
    AUTH_BASE_URL = os.getenv("AUTH_BASE_URL")

    # -------------------------------------------------------
    # INTERNAL VERGE ROUTES
    # -------------------------------------------------------
    app.include_router(verge_routes_router)

    # -------------------------------------------------------
    # MICROSERVICE BOOTSTRAP ON STARTUP
    # -------------------------------------------------------
    @app.on_event("startup")
    async def verge_bootstrap():
        print("🔥 Verge Auth started")

        # 🔐 Load JWT public key FIRST (retry-safe)
        await load_public_key(force=True)

        await asyncio.sleep(2)
        REGISTERED_ROUTES.clear()

        print("📌 Collecting routes...")

        for route in app.routes:
            try:
                path = getattr(route, "path", None)
                methods = getattr(route, "methods", [])

                if not path:
                    continue

                if path.startswith(("/docs", "/openapi", "/__verge__")):
                    continue

                for m in methods:
                    if m in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                        REGISTERED_ROUTES.append(
                            {"path": path, "method": m}
                        )

            except Exception as e:
                print("❌ Error collecting route:", e)

        print("\n📡 Registering service with Verge Auth...")

        async with httpx.AsyncClient() as client:
            if AUTH_REGISTER_URL:
                try:
                    resp = await _post_with_retries(
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
                    print(
                        "📡 Registration response:",
                        resp.status_code,
                        resp.text,
                    )
                except Exception as e:
                    print("❌ Registration failed:", e)

            if AUTH_ROUTE_SYNC_URL:
                try:
                    resp = await _post_with_retries(
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
                    print(
                        "📡 Route sync response:",
                        resp.status_code,
                        resp.text,
                    )
                except Exception as e:
                    print("❌ Route sync failed:", e)

    # -------------------------------------------------------
    # CENTRAL AUTHZ MIDDLEWARE
    # -------------------------------------------------------
    @app.middleware("http")
    async def central_auth(request: Request, call_next):
        path = request.url.path

        SKIP_PATHS = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/service-registry/register",
            "/route-sync",
            "/__verge__",
        }

        if path in SKIP_PATHS or path.startswith("/__verge__"):
            return await call_next(request)

        token = None

        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

        if not token and "session" in request.scope:
            token = request.scope["session"].get("access_token")

        # ---------------------------------------------------
        # AUTH CODE EXCHANGE
        # ---------------------------------------------------
        if not token and "code" in request.query_params:
            code = request.query_params.get("code")

            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.post(
                        f"{AUTH_BASE_URL}/auth/exchange",
                        json={"code": code},
                        headers={
                            "X-Client-Id": os.getenv("VERGE_CLIENT_ID") or "",
                            "X-Client-Secret": os.getenv("VERGE_CLIENT_SECRET") or "",
                        },
                    )
                    resp.raise_for_status()
                    token = resp.json().get("access_token")

                    if not token:
                        return JSONResponse(
                            {"detail": "Authorization failed: no token returned"},
                            status_code=401,
                        )

            except Exception as e:
                return JSONResponse(
                    {"detail": "Authorization failed", "error": str(e)},
                    status_code=401,
                )

        if not token:
            if "text/html" in request.headers.get("accept", ""):
                return RedirectResponse(
                    f"{AUTH_LOGIN_URL}?redirect_url={quote(str(request.url))}"
                )
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        # ---------------------------------------------------
        # LOCAL JWT VERIFICATION
        # ---------------------------------------------------
        try:
            if not JWT_PUBLIC_KEY:
                await load_public_key(force=True)

            if not JWT_PUBLIC_KEY:
                return JSONResponse(
                    {"detail": "Auth key not ready"},
                    status_code=503,
                )

            payload = jwt.decode(
                token,
                JWT_PUBLIC_KEY,
                algorithms=JWT_ALGORITHMS,
                options={"require": ["exp", "iat"]},
            )

        except jwt.ExpiredSignatureError:
            return JSONResponse({"detail": "Token expired"}, status_code=401)
        except jwt.InvalidTokenError:
            return JSONResponse({"detail": "Invalid token"}, status_code=401)
        except Exception as e:
            return JSONResponse(
                {"detail": "Auth verification failed", "error": str(e)},
                status_code=401,
            )

        # ---------------------------------------------------
        # CENTRAL INTROSPECTION CHECK (session + revocation)
        # ---------------------------------------------------
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(INTROSPECT_URL,
                                         headers={
                                             "Authorization": f"Bearer {token}",
                                             "X-Client-Id": os.getenv("VERGE_CLIENT_ID") or "",
                                             "X-Client-Secret": os.getenv("VERGE_CLIENT_SECRET") or "",
                                         },
                                         )

                data = resp.json()
                if not data.get("active"):
                    return JSONResponse(
                        {"detail": "Session inactive",
                            "reason": data.get("reason")},
                        status_code=401,
                    )

                # optionally enrich request with user info
                request.state.introspect = data

        except Exception as e:
            return JSONResponse(
                {"detail": "Auth introspection failed", "error": str(e)},
                status_code=401,
            )

        # ---------------------------------------------------
        # PERMISSION CHECK
        # ---------------------------------------------------
        request.state.user = payload
        permissions = payload.get("roles") or []

        route_obj = request.scope.get("route")
        route_path = route_obj.path if route_obj else path
        method = request.method

        required_key = f"{SERVICE_NAME}:{route_path}:{method}".lower()
        normalized_permissions = [p.lower() for p in permissions]

        if required_key not in normalized_permissions:
            return JSONResponse(
                {"detail": "Contact admin for access"},
                status_code=403,
            )

        return await call_next(request)
