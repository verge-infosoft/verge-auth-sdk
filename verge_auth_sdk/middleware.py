from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
import httpx
import os
import asyncio
import jwt
from typing import List
from .secret_provider import get_secret
from .verge_routes import router as verge_routes_router


def is_request_secure(request: Request) -> bool:

    if request.url.scheme == "https":
        return True

    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto and forwarded_proto.lower() == "https":
        return True

    return False


REGISTERED_ROUTES: List = []

JWT_PUBLIC_KEY: str | None = None
JWT_KEY_ID: str | None = None
JWT_ALGORITHMS = ["RS256"]


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


async def load_public_key(force: bool = False):
    global JWT_PUBLIC_KEY, JWT_KEY_ID

    AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "").rstrip("/")

    if JWT_PUBLIC_KEY and not force:
        return

    AUTH_PUBLIC_KEY_URL = f"{AUTH_BASE_URL}/auth/keys/public"
    if not AUTH_PUBLIC_KEY_URL:
        print("❌ AUTH_PUBLIC_KEY_URL not set! Please Set it.")
        return

    try:
        async with httpx.AsyncClient(timeout=50) as client:
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


def add_central_auth(app: FastAPI):
    AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "").rstrip("/")
    SERVICE_NAME = os.getenv("SERVICE_NAME")
    SERVICE_BASE_URL = os.getenv("SERVICE_BASE_URL")
    CLIENT_ID = os.getenv("VERGE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("VERGE_CLIENT_SECRET")
    VERGE_SERVICE_SECRET = get_secret("VERGE_SERVICE_SECRET")

    AUTH_REGISTER_URL = f"{AUTH_BASE_URL}/service-registry/register"
    AUTH_ROUTE_SYNC_URL = f"{AUTH_BASE_URL}/route-sync"
    INTROSPECT_URL = f"{AUTH_BASE_URL}/introspect"

    app.include_router(verge_routes_router)

    @app.post("/__verge__/set-cookie")
    def verge_set_cookie(request: Request):
        auth = request.headers.get("authorization")
        if not auth:
            return JSONResponse({"detail": "Missing Authorization header"}, status_code=401)

        token = auth.split(" ")[1]

        response = JSONResponse({"ok": True})
        response.set_cookie(
            "verge_access",
            token,
            httponly=True,
            secure=is_request_secure(request),
            samesite="None",
            path="/",
        )
        return response

    @app.on_event("startup")
    async def verge_bootstrap():
        print("🔥 Verge Auth started")

        # Load JWT public key
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
                        REGISTERED_ROUTES.append({"path": path, "method": m})

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

    @app.middleware("http")
    async def central_auth(request: Request, call_next):
        path = request.url.path

        SKIP_PATHS = {
            "/service-registry/register",
            "/route-sync",
            "/__verge__",
        }

        # Safer matching (handles trailing slash)
        normalized_path = path.rstrip("/")
        if normalized_path in SKIP_PATHS or path.startswith("/__verge__"):
            return await call_next(request)

        # ---------------------------------------------------
        # STEP 1 — HANDLE AUTH CODE EXCHANGE (SERVICE-SIDE ONLY)
        # ---------------------------------------------------
        # NOTE: The auth frontend already exchanges codes via /auth/exchange
        # This middleware only needs to handle codes coming from /services/launch
        # which generates codes for microservice access

        # code = request.query_params.get("code")
        # print("code in request param", code)

        # if code:
        #     # Check if we already have a valid token cookie
        #     existing_token = request.cookies.get("verge_access")
        #     print("existing token ", existing_token)
        #     if existing_token:
        #         # Already authenticated - just clean URL and proceed
        #         clean_url = str(request.url.remove_query_params("code"))
        #         print("clean_url RedirectResponse", clean_url)
        #         return RedirectResponse(clean_url, status_code=302)

        #     # Exchange code for token (from /services/launch flow)
        #     try:
        #         async with httpx.AsyncClient(timeout=30) as client:
        #             resp = await client.post(
        #                 f"{AUTH_BASE_URL}/auth/exchange",
        #                 json={"code": code},
        #                 headers={
        #                     "X-Client-Id": CLIENT_ID or "",
        #                     "X-Client-Secret": CLIENT_SECRET or "",
        #                 },
        #             )
        #             resp.raise_for_status()
        #             data = resp.json()
        #             token = data.get("access_token")

        #             if not token:
        #                 return JSONResponse(
        #                     {"detail": "Authorization failed: no token returned"},
        #                     status_code=401,
        #                 )

        #             # Set cookie with token and redirect to clean URL
        #             clean_url = str(request.url.remove_query_params("code"))
        #             response = RedirectResponse(clean_url, status_code=302)
        #             print("clean url when no existinig toke ", clean_url)
        #             response.set_cookie(
        #                 key="verge_access",
        #                 value=token,
        #                 httponly=True,
        #                 secure=is_request_secure(request),
        #                 samesite="lax",
        #                 path="/",
        #                 max_age=28800,  # 8 hours to match session
        #             )

        #             return response

        #     except httpx.HTTPStatusError as e:
        #         error_detail = e.response.text if hasattr(
        #             e.response, 'text') else str(e)
        #         print(f"❌ Code exchange failed: {error_detail}")
        #         return JSONResponse(
        #             {
        #                 "detail": "Authorization code exchange failed",
        #                 "error": error_detail,
        #                 "status_code": e.response.status_code if hasattr(e.response, 'status_code') else 500
        #             },
        #             status_code=401,
        #         )
        #     except Exception as e:
        #         print(f"❌ Code exchange error: {str(e)}")
        #         return JSONResponse(
        #             {"detail": "Authorization failed", "error": str(e)},
        #             status_code=401,
        #         )

        # ---------------------------------------------------
        # STEP 2 — COLLECT TOKEN (cookie → header → session)
        # ---------------------------------------------------
        token = request.cookies.get("verge_access")

        if not token:
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()

        if not token and "session" in request.scope:
            token = request.scope["session"].get("access_token")

        _raw_public = os.getenv("PUBLIC_PATHS", "")
        PUBLIC_PATHS = {
            "/" + p.strip("/ ")
            for p in _raw_public.split(",")
            if p.strip()
        }

        if not token:
            if normalized_path in PUBLIC_PATHS:
                return await call_next(request)

            login_url = f"{os.getenv('AUTH_LOGIN_URL')}?redirect_url={request.url}"

            print("Login_Url ***", login_url)

            return RedirectResponse(login_url, status_code=302)

        try:
            if not JWT_PUBLIC_KEY:
                await load_public_key(force=True)

            if not JWT_PUBLIC_KEY:
                return JSONResponse(
                    {"detail": "Auth key not ready, please try again"},
                    status_code=503,
                )

            payload = jwt.decode(
                token,
                JWT_PUBLIC_KEY,
                algorithms=JWT_ALGORITHMS,
                options={"require": ["exp", "iat"]},
            )

        except jwt.ExpiredSignatureError:
            response = RedirectResponse(
                f"{os.getenv('AUTH_LOGIN_URL')}?redirect_url={request.url}&reason=expired",
                status_code=302
            )
            response.delete_cookie("verge_access")
            return response

        except jwt.InvalidTokenError as e:
            response = RedirectResponse(
                f"{os.getenv('AUTH_LOGIN_URL')}?redirect_url={request.url}&reason=invalid",
                status_code=302
            )
            response.delete_cookie("verge_access")
            return response

        except Exception as e:
            return JSONResponse(
                {"detail": "Token verification failed", "error": str(e)},
                status_code=401,
            )

        if INTROSPECT_URL:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.post(
                        INTROSPECT_URL,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "X-Client-Id": CLIENT_ID or "",
                            "X-Client-Secret": CLIENT_SECRET or "",
                        },
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        if not data.get("active"):
                            response = RedirectResponse(
                                f"{os.getenv('AUTH_LOGIN_URL')}?redirect_url={request.url}&reason=inactive",
                                status_code=302
                            )
                            response.delete_cookie("verge_access")
                            return response

                        request.state.introspect = data
                    else:
                        response = RedirectResponse(
                            f"{os.getenv('AUTH_LOGIN_URL')}?redirect={request.url}",
                            status_code=302
                        )
                        response.delete_cookie("verge_access")
                        return response

            except Exception as e:
                print(f"⚠️  Introspection failed: {e}")

        request.state.user = payload
        permissions = payload.get("roles") or []

        route_obj = request.scope.get("route")
        route_path = route_obj.path if route_obj else path
        method = request.method

        if normalized_path in PUBLIC_PATHS:
            return await call_next(request)

        required_key = f"{SERVICE_NAME}:{route_path}:{method}".lower()
        normalized_permissions = [p.lower() for p in permissions]

        if required_key not in normalized_permissions:
            return JSONResponse(
                {
                    "detail": "Insufficient permissions. Contact admin for access.",
                    "required": required_key,
                    "user_permissions": permissions
                },
                status_code=403,
            )

        return await call_next(request)
