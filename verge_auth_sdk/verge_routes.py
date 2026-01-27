from fastapi import APIRouter, Request, HTTPException
from .secret_provider import get_secret

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
