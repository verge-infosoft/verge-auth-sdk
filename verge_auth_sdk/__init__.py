# verge_auth_sdk/__init__.py
"""
verge_auth_sdk package public API.
Exports:
 - add_central_auth(app)  -> middleware to attach to Python app
 - get_secret(name)       -> secret retrieval helper
"""
from .middleware import add_central_auth
from .secret_provider import get_secret
from .verge_routes import verge_internal_routes

__all__ = ["add_central_auth", "get_secret", "verge_internal_routes"]
