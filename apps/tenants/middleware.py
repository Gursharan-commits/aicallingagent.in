"""
Tenant context middleware.

Reads `tenant_id` from the JWT access token on every request and stores it
in a thread-local so RegionRouter can route DB queries to the correct
regional shard without an explicit `using()` or hints kwarg on every queryset.

Usage — add to MIDDLEWARE *after* AuthenticationMiddleware:
    'apps.tenants.middleware.TenantContextMiddleware',
"""

import threading
import logging
from typing import Optional

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# ── Thread-local storage ─────────────────────────────────────────────────────
_thread_locals = threading.local()


def get_current_tenant_id() -> Optional[int]:
    """Return the tenant_id bound to the current request thread, or None."""
    return getattr(_thread_locals, "tenant_id", None)


def get_current_region() -> Optional[str]:
    """Return the tenant region ('IN' | 'UK' | None) for the current thread."""
    return getattr(_thread_locals, "region", None)


def set_tenant_context(tenant_id: Optional[int], region: Optional[str]) -> None:
    """Explicitly set tenant context (useful in Celery tasks and tests)."""
    _thread_locals.tenant_id = tenant_id
    _thread_locals.region = region


def clear_tenant_context() -> None:
    """Remove tenant context at end of request/task."""
    _thread_locals.tenant_id = None
    _thread_locals.region = None


# ── Middleware ────────────────────────────────────────────────────────────────

class TenantContextMiddleware(MiddlewareMixin):
    """
    Extracts tenant_id + region from the validated JWT payload and stores
    them in thread-locals for the duration of the request.

    The JWT serializer (TenantTokenObtainPairSerializer) already embeds
    `tenant_id` and `role` so we can skip a DB lookup here.

    For non-authenticated requests (public endpoints), tenant_id is None and
    RegionRouter defaults to 'default'.
    """

    def process_request(self, request) -> None:
        # Reset from any previous request that ran on this thread
        clear_tenant_context()

        # DRF authenticates lazily; access request.auth if already resolved,
        # otherwise inspect the raw header so we can set context before views run.
        tenant_id: Optional[int] = None
        region: Optional[str] = None

        try:
            # If DRF has already populated request.auth (JWT payload dict)
            if hasattr(request, "auth") and request.auth:
                tenant_id = request.auth.get("tenant_id")
            else:
                # Fallback: decode JWT header manually without DB lookup.
                # We only need the payload claims, not signature verification
                # (DRF/SimpleJWT still performs that in its authenticator).
                auth_header = request.META.get("HTTP_AUTHORIZATION", "")
                if auth_header.startswith("Bearer "):
                    import base64
                    import json as _json

                    raw_token = auth_header.split(" ", 1)[1]
                    parts = raw_token.split(".")
                    if len(parts) == 3:
                        # Base64url-decode the payload segment
                        padded = parts[1] + "=" * (-len(parts[1]) % 4)
                        payload = _json.loads(base64.urlsafe_b64decode(padded))
                        tenant_id = payload.get("tenant_id")

            # Resolve region from Tenant table — one cheap PK lookup cached by ORM.
            if tenant_id is not None:
                from apps.tenants.models import Tenant

                try:
                    tenant = Tenant.objects.get(pk=tenant_id)
                    region = tenant.region
                except Tenant.DoesNotExist:
                    logger.warning("TenantContextMiddleware: unknown tenant_id=%s", tenant_id)

        except Exception as exc:  # noqa: BLE001
            logger.debug("TenantContextMiddleware: could not extract tenant — %s", exc)

        set_tenant_context(tenant_id, region)

    def process_response(self, request, response):  # noqa: PLR0913
        clear_tenant_context()
        return response

    def process_exception(self, request, exception):
        clear_tenant_context()
