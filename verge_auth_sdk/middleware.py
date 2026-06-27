from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
import httpx

import os

import asyncio

import jwt

import json

from typing import List

from .helpers import (
    get_cookie_settings,
    post_with_retries,
)
from .verge_routes import router as verge_routes_router


# -------------------------------------------------------------------
# Path Matching for Parametrized Routes
# -------------------------------------------------------------------

def match_path_pattern(pattern: str, path: str) -> bool:
    pattern_parts = [part for part in pattern.split("/") if part]
    path_parts = [part for part in path.split("/") if part]

    if len(pattern_parts) != len(path_parts):
        return False

    for pattern_part, path_part in zip(pattern_parts, path_parts):
        if pattern_part.startswith("{") and pattern_part.endswith("}"):
            continue
        if pattern_part != path_part:
            return False

    return True


def find_registered_route(path: str, method: str) -> dict | None:
    for route in REGISTERED_ROUTES:
        if route["method"] == method and match_path_pattern(route["path"], path):
            return route
    return None


# -------------------------------------------------------------------
# Audit Logging
# -------------------------------------------------------------------

ENABLE_AUDIT_LOGGING = os.getenv("ENABLE_AUDIT_LOGGING", "false").lower() == "true"


async def send_audit_log(
    auth_base_url: str,
    service_name: str,
    user_id: str,
    user_email: str,
    organization_id: int,
    tenant_id: int,
    action: str,
    resource: str,
    endpoint: str,
    method: str,
    ip: str,
    user_agent: str,
):
    """
    Send audit log to Verge Auth asynchronously.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{auth_base_url}/audit/ingest",
                json={
                    "user_id": str(user_id),
                    "user_email": user_email,
                    "action": action,
                    "resource": resource,
                    "endpoint": endpoint,
                    "method": method,
                    "source": "external_service",
                    "ip": ip,
                    "user_agent": user_agent,
                    "service_name": service_name,
                    "organization_id": organization_id,
                    "tenant_id": tenant_id,
                },
            )
    except Exception as e:
        # Don't fail the request if audit logging fails
        print(f"[CENTRAL_AUTH] Audit logging failed: {e}", flush=True)


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
# Permission Resolver (for Redis caching mode)
# -------------------------------------------------------------------

async def resolve_permissions_from_auth_server(permission_set_id: str) -> List[str]:
    """
    Fetch permissions from Verge Auth API using permission_set_id.
    Used when PERMISSIONS_IN_TOKEN=false (Redis caching mode).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{AUTH_BASE_URL}/permissions/resolve",
                params={"permission_set_id": permission_set_id}
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("permissions", [])
    except Exception as e:
        log(f"Failed to resolve permissions from auth server: {e}")
        return []


# -------------------------------------------------------------------
# Load JWT Public Key
# -------------------------------------------------------------------

async def load_public_key(force: bool = False):
    global JWT_PUBLIC_KEY, JWT_KEY_ID

    if JWT_PUBLIC_KEY and not force:
        return

    auth_base_url = os.getenv("AUTH_BASE_URL", "").rstrip("/")
    if not auth_base_url:
        raise RuntimeError("AUTH_BASE_URL not configured")

    AUTH_PUBLIC_KEY_URL = f"{auth_base_url}/auth/keys/public"

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
    global AUTH_BASE_URL
    AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "").rstrip("/")
    AUTH_FRONTEND_URL = os.getenv("AUTH_FRONTEND_URL", "").rstrip("/")
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
        # ------------------------------------------------------------
        # Step 1 — Populate registered routes FIRST (local, never fails).
        # This must run before any network call so that parameterized
        # route matching always works even if the auth server is briefly
        # unreachable during container startup.
        # ------------------------------------------------------------
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

        log(f"Registered {len(REGISTERED_ROUTES)} routes at startup")

        # ------------------------------------------------------------
        # Step 2 — Load the JWT public key (resilient: failures here must
        # not prevent route registration; it is lazily reloaded on the
        # first request if needed).
        # ------------------------------------------------------------
        try:
            await load_public_key(force=True)
        except Exception as e:
            log(f"Startup load_public_key failed (will retry lazily): {e}")

        await asyncio.sleep(1)

        # ------------------------------------------------------------
        # Step 3 — Register service & sync routes (resilient).
        # ------------------------------------------------------------
        try:
            async with httpx.AsyncClient() as client:
                await post_with_retries(
                    client,
                    AUTH_REGISTER_URL,
                    json={
                        "service_name": SERVICE_NAME,
                        "base_url": SERVICE_BASE_URL,
                        "frontend_url": SERVICE_FRONTEND_URL,
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
        except Exception as e:
            log(f"Startup service/route sync failed: {e}")

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
        if code:
            log("Auth code detected")

            # If cookie already exists → just remove code and go to frontend
            if request.cookies.get("verge_access"):
                log("Cookie exists, removing code and redirecting to frontend")

                # Convert API path to frontend path for redirect
                frontend_path = request.url.path
                if frontend_path.startswith('/api/'):
                    # Remove /api prefix for frontend
                    frontend_path = frontend_path[4:]  # Use slicing instead of replace
                    if not frontend_path:
                        frontend_path = '/'

                return RedirectResponse(
                    f"{SERVICE_FRONTEND_URL}{frontend_path}",
                    status_code=302,
                )

            log("Exchanging auth code with Verge Auth")

            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        f"{AUTH_BASE_URL}/auth/exchange",
                        json={"code": code, "service_name": SERVICE_NAME},
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
                        frontend_path = frontend_path[4:]  # Use slicing instead of replace
                        if not frontend_path:
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
            except httpx.HTTPStatusError as e:
                log(f"Auth code exchange failed: {e.response.status_code}")
                return RedirectResponse(
                    f"{AUTH_BASE_URL}/login?redirect_url={SERVICE_FRONTEND_URL}/auth/callback&reason=exchange_failed",
                    status_code=302,
                )
            except Exception as e:
                log(f"Auth code exchange error: {e}")
                return RedirectResponse(
                    f"{AUTH_BASE_URL}/login?redirect_url={SERVICE_FRONTEND_URL}/auth/callback&reason=exchange_error",
                    status_code=302,
                )

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
        
        # Try to parse as JSON first, fallback to comma-separated
        try:
            if raw_public_paths.startswith("["):
                # Parse as JSON array
                parsed_paths = json.loads(raw_public_paths)
                PUBLIC_PATHS = {"/" + p.strip("/ ") for p in parsed_paths if p.strip()}
            else:
                # Parse as comma-separated
                PUBLIC_PATHS = {
                    "/" + p.strip("/ ")
                    for p in raw_public_paths.split(",")
                    if p.strip()
                }
        except json.JSONDecodeError as e:
            log(f"Failed to parse PUBLIC_PATHS as JSON: {e}, falling back to comma-separated")
            PUBLIC_PATHS = {
                "/" + p.strip("/ ")
                for p in raw_public_paths.split(",")
                if p.strip()
            }

        # ------------------------------------------------------------
        # Check public paths BEFORE token verification
        # ------------------------------------------------------------
        if normalized_path in PUBLIC_PATHS:
            log("Public path accessed, allowing")
            return await call_next(request)

        frontend_target = f"{SERVICE_FRONTEND_URL}{request.url.path}"

        # Use /auth/callback for login redirect (matches React SDK default)
        login_url = (
            f"{AUTH_FRONTEND_URL}/login?"
            f"redirect_url={SERVICE_FRONTEND_URL}/auth/callback"
        )

        if not token:
            log(f"No token found, redirecting to login: {login_url}")
            # Check if request is XHR/API request (browser won't follow cross-origin 302 for XHR)
            accept_header = request.headers.get("accept", "")
            requested_with = request.headers.get("x-requested-with", "")
            is_xhr = "application/json" in accept_header or requested_with == "XMLHttpRequest"

            if is_xhr:
                # Return 401 with redirect URL in header for XHR requests
                return JSONResponse(
                    {"detail": "Authentication required", "redirect_url": login_url},
                    status_code=401,
                    headers={"X-Auth-Redirect-Url": login_url}
                )
            else:
                # Return 302 redirect for browser navigation
                return RedirectResponse(login_url, status_code=302)

        # ------------------------------------------------------------
        # Step 3 — Verify JWT
        # ------------------------------------------------------------
        try:
            # Validate kid header matches loaded key
            token_header = jwt.get_unverified_header(token)
            token_kid = token_header.get("kid")
            if token_kid and token_kid != JWT_KEY_ID:
                log(f"JWT kid mismatch: {token_kid} (expected: {JWT_KEY_ID}), reloading public key")
                await load_public_key(force=True)

            payload = jwt.decode(
                token,
                JWT_PUBLIC_KEY,
                algorithms=JWT_ALGORITHMS,
                options={"require": ["exp", "iat", "aud"], "verify_aud": True},
                audience=SERVICE_NAME,
            )

            log("JWT successfully decoded")

            # Validate required fields
            user_id = payload.get("user_id")
            organization_id = payload.get("organization_id")
            scope = payload.get("scope")

            if not user_id or not organization_id or not scope:
                log("JWT missing required fields (user_id, organization_id, or scope)")
                response = RedirectResponse(
                    f"{AUTH_BASE_URL}/login?"
                    f"redirect_url={SERVICE_FRONTEND_URL}/auth/callback&reason=invalid_token",
                    status_code=302,
                )
                response.delete_cookie("verge_access")
                return response

            # Handle permission resolution (legacy vs Redis caching mode)
            permissions = payload.get("permissions", [])
            permission_set_id = payload.get("permission_set_id")
            
            if permission_set_id and not permissions:
                # Redis caching mode: fetch permissions from auth server
                log(f"Detected Redis caching mode, resolving permissions for set: {permission_set_id}")
                permissions = await resolve_permissions_from_auth_server(permission_set_id)
                log(f"Resolved {len(permissions)} permissions from auth server")
            elif permissions:
                # Legacy mode: permissions are in JWT
                log(f"Legacy mode: using {len(permissions)} permissions from JWT")
            else:
                log("No permissions found in JWT")

            request.state.auth = {
                "auth_user_id": user_id,
                "email": payload.get("email", ""),
                "first_name": payload.get("first_name", ""),
                "last_name": payload.get("last_name", ""),
                "organization_id": organization_id,
                "organization_name": payload.get("organization_name", ""),
                "tenant_id": payload.get("tenant_id"),
                "tenant_name": payload.get("tenant_name", ""),
                "scope": scope,
                "roles": payload.get("roles", []),
                "permissions": permissions,
                "is_super_admin": payload.get("is_super_admin", False),
            }
        except jwt.ExpiredSignatureError:
            log("JWT expired, redirecting to login")
            response = RedirectResponse(
                f"{AUTH_BASE_URL}/login?"
                f"redirect_url={SERVICE_FRONTEND_URL}/auth/callback&reason=expired",
                status_code=302,
            )
            response.delete_cookie("verge_access")
            return response

        except jwt.InvalidAudienceError:
            log("JWT audience mismatch, redirecting to login")
            response = RedirectResponse(
                f"{AUTH_BASE_URL}/login?"
                f"redirect_url={SERVICE_FRONTEND_URL}/auth/callback&reason=invalid_audience",
                status_code=302,
            )
            response.delete_cookie("verge_access")
            return response

        except jwt.InvalidTokenError as e:
            log(f"Invalid JWT: {str(e)}")
            response = RedirectResponse(
                f"{AUTH_BASE_URL}/login?"
                f"redirect_url={SERVICE_FRONTEND_URL}/auth/callback&reason=invalid",
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
        matched_route = find_registered_route(original_path, method)

        if not matched_route:
            # Try to find a matching route by adding common prefixes
            common_prefixes = ["/api", "/v1", "/api/v1", "/v2", "/api/v2"]

            for prefix in common_prefixes:
                potential_path = prefix + original_path
                # Try both with and without trailing slash
                potential_paths = [potential_path, potential_path + "/", potential_path.rstrip('/') + '/']

                for path_variant in potential_paths:
                    candidate_route = find_registered_route(path_variant, method)
                    if candidate_route:
                        route_path = path_variant
                        path_prefix = prefix
                        matched_route = candidate_route
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
                fallback_route = find_registered_route(fallback_path, method)
                if fallback_route:
                    route_path = fallback_path
                    path_prefix = "/api"
                    matched_route = fallback_route
                    log(f"Fallback: Using /api prefix with trailing slash -> {route_path}")
                else:
                    route_path = "/api" + original_path
                    path_prefix = "/api"
                    matched_route = find_registered_route(route_path, method)
                    log(f"Fallback: Using /api prefix -> {route_path}")
        else:
            log(f"Route found directly: {original_path}")

        # Resolve the matched route PATTERN so parameterized routes map to their
        # registered permission key (e.g. /api/job-portal/jobs/1 -> /api/job-portal/jobs/{job_id}).
        # Without this, the concrete path with real IDs is used and never matches the
        # parameterized permission stored in the auth server.
        matched_pattern = matched_route['path'] if matched_route else None

        # Use standard permission format that matches auth server (no trailing slash)
        permission_path = (matched_pattern or route_path).rstrip('/')  # Remove trailing slash for permissions
        required_key = f"{SERVICE_NAME}:{permission_path}:{method}".lower()

        log(f"Request URL: {request.url}")
        log(f"Original path: {original_path}")
        log(f"Route path: {route_path}")
        log(f"Matched pattern: {matched_pattern}")
        log(f"Request method: {method}")
        log(f"SERVICE_NAME: {SERVICE_NAME}")
        log(f"Detected prefix: {path_prefix}")

        log(f"=== AUTHORIZATION DEBUG ===")
        log(f"Required permission: {required_key}")
        log(f"User permissions count: {len(permissions)}")

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

        # ------------------------------------------------------------
        # Step 6 — Send audit log (if enabled)
        # ------------------------------------------------------------
        if ENABLE_AUDIT_LOGGING:
            ctx = request.state.auth
            user_id = ctx.get("auth_user_id")
            user_email = payload.get("email", "")
            organization_id = ctx.get("organization_id")
            tenant_id = ctx.get("tenant_id")

            # Determine action type based on request
            action = "api_call"
            if original_path.startswith("/") and not original_path.startswith("/api"):
                action = "page_visit"

            # Send audit log asynchronously (fire and forget)
            asyncio.create_task(
                send_audit_log(
                    auth_base_url=AUTH_BASE_URL,
                    service_name=SERVICE_NAME,
                    user_id=user_id,
                    user_email=user_email,
                    organization_id=organization_id,
                    tenant_id=tenant_id,
                    action=action,
                    resource=original_path,
                    endpoint=original_path,
                    method=method,
                    ip=request.client.host if request.client else "",
                    user_agent=request.headers.get("user-agent", ""),
                )
            )

        # Use the auto-detected route path for internal routing
        if route_path != original_path:
            # Modify the request scope for internal routing
            log(f"Updating request scope: {original_path} -> {route_path}")
            request.scope["path"] = route_path
            request.scope["raw_path"] = route_path.encode()
        else:
            log(f"Using original path: {original_path}")

        return await call_next(request)
