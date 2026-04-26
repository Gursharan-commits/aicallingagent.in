from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class TenantTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer that embeds tenant context and 4-tier role
    into the access token payload.

    Claims added:
        tenant_id   — FK to Tenant (null for super_admin)
        role        — one of: super_admin | admin | tenant_admin | tenant_user
        email       — user's email address
        cloud_region — tenant's data-residency AWS region (ap-south-1 | eu-west-2)
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["tenant_id"] = user.tenant_id
        token["role"] = user.role
        token["email"] = user.email
        token["cloud_region"] = (
            user.tenant.cloud_region if user.tenant_id else None
        )
        return token


class TenantTokenObtainPairView(TokenObtainPairView):
    """Login view that returns the enriched JWT."""
    serializer_class = TenantTokenObtainPairSerializer
