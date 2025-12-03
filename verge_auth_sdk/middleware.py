from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from .secret_provider import get_secret
from .verge_routes import router as verge_routes_router
import httpx
import os

REGISTERED_ROUTES = []


def add_central_auth(app: FastAPI):

    AUTH_INTROSPECT_URL = os.getenv("AUTH_INTROSPECT_URL")
    AUTH_LOGIN_URL = os.getenv("AUTH_LOGIN_URL")
    CLIENT_ID = os.getenv("VERGE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("VERGE_CLIENT_SECRET")

    # -----------------------------------------------
    # Attach internal SDK routes FIRST
    # -----------------------------------------------
    app.include_router(verge_routes_router)

    # -----------------------------------------------
    # Startup: collect routes + register service
    # -----------------------------------------------
    @app.on_event("startup")
    async def verge_bootstrap():
        print("🔥 Verge bootstrap started")

        # STEP 1 — Collect routes
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

        print("✅ Collected:", REGISTERED_ROUTES)

        # STEP 2 — Register service in auth server
        SERVICE_NAME = os.getenv("SERVICE_NAME")
        SERVICE_BASE_URL = os.getenv("SERVICE_BASE_URL")
        AUTH_REGISTER_URL = os.getenv("AUTH_REGISTER_URL")
        VERGE_SECRET = get_secret("VERGE_SERVICE_SECRET")

        print("\n📡 Registering service with Auth Service...")
        print("SERVICE_NAME =", SERVICE_NAME)
        print("SERVICE_BASE_URL =", SERVICE_BASE_URL)
        print("AUTH_REGISTER_URL =", AUTH_REGISTER_URL)

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    AUTH_REGISTER_URL,
                    params={"name": SERVICE_NAME,
                            "base_url": SERVICE_BASE_URL},
                    headers={"X-Verge-Service-Secret": VERGE_SECRET},
                )
                print("📡 Registration Response:", resp.status_code, resp.text)
            except Exception as e:
                print("❌ Registration failed:", e)

    # STEP 3 — Attach middleware AFTER registration
    @app.middleware("http")
    async def central_auth(request: Request, call_next):
        path = request.url.path

        # Whitelist internal + health
        if path.startswith("/__verge__"):
            return await call_next(request)

        if path in {"/health", "/docs", "/openapi.json"}:
            return await call_next(request)

        # Extract JWT
        token = None
        auth = request.headers.get("authorization")

        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ")[1]

        if not token:
            token = request.cookies.get("access_token")

        if not token:
            if "text/html" in request.headers.get("accept", ""):
                return RedirectResponse(f"{AUTH_LOGIN_URL}?redirect_url={request.url}")
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        # Validate token
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                res = await client.post(
                    AUTH_INTROSPECT_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Client-Id": CLIENT_ID,
                        "X-Client-Secret": CLIENT_SECRET,
                    },
                )
                data = res.json()
        except:
            return JSONResponse({"detail": "Auth service unreachable"}, status_code=503)

        if not data.get("active"):
            return JSONResponse({"detail": "Session expired"}, status_code=401)

        request.state.user = data.get("user")
        request.state.roles = data.get("roles")

        return await call_next(request)
