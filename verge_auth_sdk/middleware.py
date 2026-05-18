from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
import httpx

import os

import asyncio

import jwt

import json

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

AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "").rstrip("/")


def log(msg: str):
    print(f"[CENTRAL_AUTH] {msg}", flush=True)


# -------------------------------------------------------------------
# Load JWT Public Key
# -------------------------------------------------------------------

async def load_public_key(force: bool = False):
    global JWT_PUBLIC_KEY, JWT_KEY_ID

    if JWT_PUBLIC_KEY and not force:
        return

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
    SERVICE_FRONTEND_URL = os.getenv("SERVICE_FRONTEND_URL")

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

        log(f"Incoming request: {request.method} {request.url}")
        log(f"Normalized path: {normalized_path}")

        # ------------------------------------------------------------
        # Skip internal paths
        # ------------------------------------------------------------
        if normalized_path.startswith("/__verge__"):
            log("Skipping internal Verge path")
            return await call_next(request)

        # ------------------------------------------------------------
        # Step 1 — Handle auth code callback
        # ------------------------------------------------------------
        code = request.query_params.get("code")
        log(f"Auth code detected: {code}")
        if code:
            log("Auth code detected")

            # If cookie already exists → just remove code and go to frontend
            if request.cookies.get("verge_access"):
                log("Cookie exists, removing code and redirecting to frontend")

                # Convert API path to frontend path for redirect
                frontend_path = request.url.path
                if frontend_path.startswith('/api/'):
                    # Remove /api prefix for frontend
                    frontend_path = frontend_path.replace('/api', '', 1)
                    if frontend_path == '':
                        frontend_path = '/'
                
                return RedirectResponse(
                    f"{SERVICE_FRONTEND_URL}{frontend_path}",
                    status_code=302,
                )

            log("Exchanging auth code with Verge Auth")

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

                # Convert API path to frontend path for redirect
                frontend_path = request.url.path
                if frontend_path.startswith('/api/'):
                    # Remove /api prefix for frontend
                    frontend_path = frontend_path.replace('/api', '', 1)
                    if frontend_path == '':
                        frontend_path = '/'
                
                response = RedirectResponse(
                    f"{SERVICE_FRONTEND_URL}{frontend_path}",
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
        log(f"Cookie token present: {'YES' if token else 'NO'}")
        if not token:
            auth = request.headers.get("authorization")
            if auth and auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1]
                log("Token extracted from Authorization header")
        
        raw_public_paths = os.getenv("PUBLIC_PATHS", "")
        log(f"Raw PUBLIC_PATHS env var: '{raw_public_paths}' (length: {len(raw_public_paths)})")
        log(f"Raw PUBLIC_PATHS repr: {repr(raw_public_paths)}")
        
        # Try to parse as JSON first, fallback to comma-separated
        try:
            if raw_public_paths.startswith("["):
                # Parse as JSON array
                parsed_paths = json.loads(raw_public_paths)
                log(f"JSON parsed paths: {parsed_paths}")
                PUBLIC_PATHS = {"/" + p.strip("/ ") for p in parsed_paths if p.strip()}
                log(f"JSON parsing successful: {PUBLIC_PATHS}")
            else:
                # Parse as comma-separated
                PUBLIC_PATHS = {
                    "/" + p.strip("/ ")
                    for p in raw_public_paths.split(",")
                    if p.strip()
                }
                log(f"Comma-separated parsing: {PUBLIC_PATHS}")
        except (json.JSONDecodeError, Exception) as e:
            log(f"Failed to parse PUBLIC_PATHS: {e}, falling back to comma-separated")
            PUBLIC_PATHS = {
                "/" + p.strip("/ ")
                for p in raw_public_paths.split(",")
                if p.strip()
            }
        
        log(f"Parsed public paths: {PUBLIC_PATHS}")

        frontend_target = f"{SERVICE_FRONTEND_URL}{request.url.path}"
        
        # Convert API path to frontend path for login redirect
        frontend_path = request.url.path
        if frontend_path.startswith('/api/'):
            # Remove /api prefix for frontend
            frontend_path = frontend_path.replace('/api', '', 1)
            if frontend_path == '':
                frontend_path = '/'
        
        login_url = (
            f"{AUTH_BASE_URL}/login?"
            f"redirect_uri={SERVICE_FRONTEND_URL}{frontend_path}"
        )
        
        if not token:
            if normalized_path in PUBLIC_PATHS:
                log("Public path accessed without token, allowing")
                return await call_next(request)

            log(f"No token found, redirecting to login: {login_url}")
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

            log("JWT successfully decoded")
            log(f"JWT payload: {payload}")

            request.state.auth = {
                "auth_user_id": payload["user_id"],
                "organization_id": payload["organization_id"],
                "tenant_id": payload.get("tenant_id"),
                "scope": payload["scope"],
                "roles": payload.get("roles", []),
                "permissions": payload.get("permissions", []),
            }
        except jwt.ExpiredSignatureError:
            log("JWT expired, redirecting to login")
            response = RedirectResponse(
                f"{AUTH_BASE_URL}/login?"
                f"redirect_uri={SERVICE_FRONTEND_URL}{frontend_path}&reason=expired",
                status_code=302,
            )
            response.delete_cookie("verge_access")
            return response

        except jwt.InvalidTokenError as e:
            log(f"Invalid JWT: {str(e)}")
            response = RedirectResponse(
                f"{AUTH_BASE_URL}/login?"
                f"redirect_uri={SERVICE_FRONTEND_URL}{frontend_path}&reason=invalid",
                status_code=302,
            )
            response.delete_cookie("verge_access")
            return response

    # ------------------------------------------------------------
        # Step 5 — Authorization check
        # ------------------------------------------------------------
        ctx = request.state.auth
        permissions = ctx.get("permissions", [])
        
        # Automatic route detection - no configuration needed
        original_path = request.url.path
        method = request.method.upper()
        
        # Auto-detect if we need to add a prefix based on registered routes
        route_path = original_path
        path_prefix = ""
        
        # Check if the original path exists in registered routes
        log(f"Available routes: {list(REGISTERED_ROUTES)[:10]}...")  # Show first 10 routes
        
        # Check direct route match (with method and path consideration)
        direct_match = any(route['path'] == original_path and route['method'] == method for route in REGISTERED_ROUTES)
        
        if not direct_match:
            # Try to find a matching route by adding common prefixes
            common_prefixes = ["/api", "/v1", "/api/v1", "/v2", "/api/v2"]
            
            for prefix in common_prefixes:
                potential_path = prefix + original_path
                # Try both with and without trailing slash
                potential_paths = [potential_path, potential_path + "/", potential_path.rstrip('/') + '/']
                
                for path_variant in potential_paths:
                    if any(route['path'] == path_variant and route['method'] == method for route in REGISTERED_ROUTES):
                        route_path = path_variant
                        path_prefix = prefix
                        log(f"Auto-detected path prefix: {original_path} -> {route_path}")
                        break
                if route_path != original_path:
                    break
            else:
                log(f"No route found for {original_path} in registered routes")
                log(f"Tried prefixes: {common_prefixes}")
                # Fallback: assume /api prefix if no route found
                # Try with trailing slash first
                fallback_path = "/api" + original_path + "/"
                if any(route['path'] == fallback_path and route['method'] == method for route in REGISTERED_ROUTES):
                    route_path = fallback_path
                    path_prefix = "/api"
                    log(f"Fallback: Using /api prefix with trailing slash -> {route_path}")
                else:
                    route_path = "/api" + original_path
                    path_prefix = "/api"
                    log(f"Fallback: Using /api prefix -> {route_path}")
        else:
            log(f"Route found directly: {original_path}")
        
        # Use standard permission format that matches auth server (no trailing slash)
        permission_path = route_path.rstrip('/')  # Remove trailing slash for permissions
        required_key = f"{SERVICE_NAME}:{permission_path}:{method}".lower()
        
        log(f"Request URL: {request.url}")
        log(f"Original path: {original_path}")
        log(f"Route path: {route_path}")
        log(f"Request method: {method}")
        log(f"SERVICE_NAME: {SERVICE_NAME}")
        log(f"Detected prefix: {path_prefix}")
        
        log(f"=== AUTHORIZATION DEBUG ===")
        log(f"Required permission: {required_key}")
        log(f"User permissions count: {len(permissions)}")
        log(f"User permissions: {permissions[:5]}...")  # Show first 5 permissions
        
        # Check if required permission exists
        permission_exists = required_key in [p.lower() for p in permissions]
        log(f"Permission check result: {permission_exists}")
        
        if not permission_exists:
            log(f"ACCESS DENIED - Missing permission: {required_key}")
            return JSONResponse(
                {
                    "detail": "Insufficient permissions",
                    "required": required_key,
                },
                status_code=403,
            )
        
        log("ACCESS GRANTED - Permission matched")
        log("Permission granted, forwarding request")
        
        # Use the auto-detected route path for internal routing
        if route_path != original_path:
            # Modify the request scope for internal routing
            log(f"Updating request scope: {original_path} -> {route_path}")
            request.scope["path"] = route_path
            request.scope["raw_path"] = route_path.encode()
        else:
            log(f"Using original path: {original_path}")
        
        return await call_next(request)
        
        
