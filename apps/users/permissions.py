from rest_framework.permissions import BasePermission


class IsSameTenant(BasePermission):
    """
    Enforces multi-tenant isolation at the API layer.
    Reads tenant_id from the JWT payload (no DB hit) and blocks any request
    where the object's tenant does not match the authenticated user's tenant.
    """
    message = "You do not have permission to access resources from another tenant."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        # Extract tenant_id from JWT claim directly
        token_tenant_id = request.auth.get('tenant_id') if request.auth else None

        # Resolve the object's tenant FK (handles both direct tenant and nested)
        if hasattr(obj, 'tenant_id'):
            return obj.tenant_id == token_tenant_id
        if hasattr(obj, 'tenant'):
            return obj.tenant.id == token_tenant_id

        return False


class IsAdminRole(BasePermission):
    """Restricts access to users with admin role (within their own tenant)."""

    def has_permission(self, request, view):
        token_role = request.auth.get('role') if request.auth else None
        return token_role == 'admin'
