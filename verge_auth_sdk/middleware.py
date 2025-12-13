from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from .secret_provider import get_secret
from .verge_routes import router as verge_routes_router
import httpx
import os
import asyncio   # ✅ needed for retry logic

REGISTERED_ROUTES = []


async def _post_with_retries(client, url, json=None, headers=None, timeout=10, retries=8, backoff=1):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = await client.post(
                url,
                json=json,
                headers=headers,
                timeout=timeout,
            )
            return resp  # success
        except Exception as e:
            last_exc = e
            print(
                f"❗ Retry {attempt}/{retries} failed for {url}: {type(e).__name__}: {e}")
            await asyncio.sleep(backoff * attempt)  # linear backoff
    raise last_exc


def add_central_auth(app: FastAPI):

    AUTH_INTROSPECT_URL = os.getenv("AUTH_INTROSPECT_URL")
    AUTH_LOGIN_URL = os.getenv("AUTH_LOGIN_URL")

    SERVICE_NAME = os.getenv("SERVICE_NAME")
    SERVICE_BASE_URL = os.getenv("SERVICE_BASE_URL")

    CLIENT_ID = os.getenv("VERGE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("VERGE_CLIENT_SECRET")

    VERGE_SERVICE_SECRET = get_secret("VERGE_SERVICE_SECRET")

    AUTH_REGISTER_URL = os.getenv("AUTH_REGISTER_URL")
    AUTH_ROUTE_SYNC_URL = os.getenv("AUTH_ROUTE_SYNC_URL")

    # -----------------------------------------------------------
    # INTERNAL VERGE ROUTES
    # -----------------------------------------------------------
    app.include_router(verge_routes_router)

    # -----------------------------------------------------------
    # MICROSERVICE BOOTSTRAP ON STARTUP
    # -----------------------------------------------------------
    @app.on_event("startup")
    async def verge_bootstrap():
        print("🔥 Verge bootstrap started")

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
                        REGISTERED_ROUTES.append({"path": path, "method": m})

            except Exception as e:
                print("❌ Error collecting route:", e)

        print("✅ Collected routes:", REGISTERED_ROUTES)

        print("\n📡 Registering service with Auth Service...")
        print("SERVICE_NAME =", SERVICE_NAME)
        print("SERVICE_BASE_URL =", SERVICE_BASE_URL)
        print("AUTH_REGISTER_URL =", AUTH_REGISTER_URL)
        print("AUTH_ROUTE_SYNC_URL =", AUTH_ROUTE_SYNC_URL)
        print("VERGE_SERVICE_SECRET =",
              VERGE_SERVICE_SECRET if VERGE_SERVICE_SECRET else "MISSING")
        print("CLIENT_ID =", CLIENT_ID if CLIENT_ID else "MISSING")
        print("CLIENT_SECRET =",
              CLIENT_SECRET if CLIENT_SECRET else "MISSING")

        async with httpx.AsyncClient() as client:
            if AUTH_REGISTER_URL:
                try:
                    resp = await _post_with_retries(
                        client,
                        AUTH_REGISTER_URL,
                        json={"service_name": SERVICE_NAME,
                              "base_url": SERVICE_BASE_URL},
                        headers={
                            "X-Client-Id": CLIENT_ID or "",
                            "X-Client-Secret": CLIENT_SECRET or "",
                            "X-Verge-Service-Secret": VERGE_SERVICE_SECRET or "",
                        },
                        timeout=10,
                        retries=8,
                        backoff=1
                    )
                    text = resp.text if hasattr(resp, "text") else await resp.text()
                    print("📡 Registration response:", resp.status_code, text)

                except Exception as e:
                    print("❌ Registration ultimately failed:",
                          type(e).__name__, str(e))

            else:
                print("⚠️ AUTH_REGISTER_URL missing")

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
                        retries=8,
                        backoff=1
                    )
                    text = resp.text if hasattr(resp, "text") else await resp.text()
                    print("📡 Route sync response:", resp.status_code, text)

                except Exception as e:
                    print("❌ Route sync ultimately failed:",
                          type(e).__name__, str(e))

            else:
                print("⚠️ AUTH_ROUTE_SYNC_URL missing")

    # -----------------------------------------------------------
    # CENTRAL AUTHZ MIDDLEWARE (unchanged)
    # -----------------------------------------------------------
    @app.middleware("http")
    async def central_auth(request: Request, call_next):
        path = request.url.path

        SKIP_PATHS = {
            "/health",
            "/docs",
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

        if not token:
            token = request.cookies.get("access_token")

        if not token:
            if "text/html" in request.headers.get("accept", ""):
                return RedirectResponse(f"{AUTH_LOGIN_URL}?redirect_url={request.url}")
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.post(
                    AUTH_INTROSPECT_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Client-Id": CLIENT_ID or "",
                        "X-Client-Secret": CLIENT_SECRET or "",
                    },
                )
                data = res.json()
        except Exception as e:
            return JSONResponse({"detail": "Auth service unreachable", "error": str(e)}, status_code=503)

        if not data.get("active"):
            return JSONResponse({"detail": "Session expired"}, status_code=401)

        request.state.user = data.get("user")
        permissions = (data.get("roles") or [])

        route_obj = request.scope.get("route")
        route_path = route_obj.path if route_obj is not None else path
        method = request.method

        required_key = f"{SERVICE_NAME}:{route_path}:{method}".lower()
        normalized_permissions = [p.lower() for p in permissions]

        if required_key not in normalized_permissions:
            return JSONResponse({"detail": "Contact admin for access"}, status_code=403)

        return await call_next(request)
