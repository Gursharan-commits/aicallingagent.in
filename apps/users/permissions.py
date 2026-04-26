"""
4-tier RBAC permission classes for Django REST Framework.

Usage example in a view:
    permission_classes = [IsSameTenant, IsTenantAdmin]

Hierarchy (additive — each class grants its tier AND all lower ones):
    SuperAdmin   > Admin > TenantAdmin > TenantUser (IsAuthenticated covers all)

All classes read role/tenant_id from the JWT payload to avoid DB lookups.
"""

from rest_framework.permissions import BasePermission

__all__ = [
    "IsSameTenant",
    "IsSuperAdmin",
    "IsAdmin",
    "IsTenantAdmin",
    "IsTenantUser",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _jwt_claim(request, key):
    """Safely extract a claim from the DRF JWT auth payload."""
    return request.auth.get(key) if request.auth else None


# ── Tenant isolation ──────────────────────────────────────────────────────────

class IsSameTenant(BasePermission):
    """
    Enforces multi-tenant object isolation at the API layer.

    - SuperAdmins bypass the tenant check (they own all tenants).
    - All other roles must have a matching tenant_id on the target object.
    """

    message = "You do not have permission to access resources from another tenant."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        role = _jwt_claim(request, "role")
        if role == "super_admin":
            return True

        token_tenant_id = _jwt_claim(request, "tenant_id")
        if token_tenant_id is None:
            return False

        if hasattr(obj, "tenant_id"):
            return obj.tenant_id == token_tenant_id
        if hasattr(obj, "tenant"):
            return obj.tenant.id == token_tenant_id
        return False


# ── Role gates ────────────────────────────────────────────────────────────────

class IsSuperAdmin(BasePermission):
    """Platform-level access only. Allows managing all tenants."""

    message = "Super Admin access required."

    def has_permission(self, request, view) -> bool:
        return _jwt_claim(request, "role") == "super_admin"


class IsAdmin(BasePermission):
    """
    Tenant Admin (full) — includes super_admin.
    Use for destructive operations within a tenant (delete configs, etc.).
    """

    message = "Admin access required."

    def has_permission(self, request, view) -> bool:
        return _jwt_claim(request, "role") in ("super_admin", "admin")


class IsTenantAdmin(BasePermission):
    """
    Tenant-level management — includes super_admin and admin.
    Use for creating/updating campaigns, agent configs, tools.
    """

    message = "Tenant Admin access required."

    def has_permission(self, request, view) -> bool:
        return _jwt_claim(request, "role") in (
            "super_admin",
            "admin",
            "tenant_admin",
        )


class IsTenantUser(BasePermission):
    """
    Basic authenticated tenant member — any of the 4 roles.
    Use for read-heavy endpoints (call logs, transcripts).
    """

    message = "Authenticated tenant user required."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and _jwt_claim(request, "role") in (
                "super_admin",
                "admin",
                "tenant_admin",
                "tenant_user",
            )
        )
