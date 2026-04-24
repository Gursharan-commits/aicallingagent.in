from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class TenantTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer that embeds tenant_id and role into the access token.
    This avoids a DB round-trip on every request — the API layer reads these
    claims directly from the token and enforces tenant isolation.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Embed tenant context into the token payload
        token['tenant_id'] = user.tenant_id
        token['role'] = user.role
        token['email'] = user.email
        return token


class TenantTokenObtainPairView(TokenObtainPairView):
    """Login view that returns our enriched JWT."""
    serializer_class = TenantTokenObtainPairSerializer
