from rest_framework import serializers, viewsets
from rest_framework.routers import DefaultRouter
from apps.tenants.models import Tenant
from apps.ai_engine.models import AIConfig
from apps.campaigns.models import Campaign
from apps.calls.models import Call
from apps.billing.models import BillingAccount
from apps.users.permissions import IsSameTenant

# ==========================================
# SERIALIZERS
# ==========================================

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = '__all__'

class AIConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIConfig
        fields = '__all__'
        read_only_fields = ['tenant']

class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = '__all__'
        read_only_fields = ['tenant']

class CallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Call
        fields = '__all__'

class BillingAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingAccount
        fields = '__all__'

# ==========================================
# VIEWSETS
# ==========================================

def _get_tenant_id(request):
    """
    Read tenant_id from JWT claim if present (production path),
    otherwise fall back to request.user.tenant_id (test force_authenticate path).
    """
    if request.auth and hasattr(request.auth, 'get'):
        return request.auth.get('tenant_id')
    if request.user and request.user.is_authenticated:
        return request.user.tenant_id
    return None


class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    """Tenants are read-only via API; created by platform admins only."""
    serializer_class = TenantSerializer
    permission_classes = [IsSameTenant]

    def get_queryset(self):
        return Tenant.objects.filter(id=_get_tenant_id(self.request))


class AIConfigViewSet(viewsets.ModelViewSet):
    serializer_class = AIConfigSerializer
    permission_classes = [IsSameTenant]

    def get_queryset(self):
        return AIConfig.objects.filter(tenant_id=_get_tenant_id(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant_id=_get_tenant_id(self.request))


class CampaignViewSet(viewsets.ModelViewSet):
    serializer_class = CampaignSerializer
    permission_classes = [IsSameTenant]

    def get_queryset(self):
        return Campaign.objects.filter(tenant_id=_get_tenant_id(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant_id=_get_tenant_id(self.request))


class CallViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CallSerializer
    permission_classes = [IsSameTenant]

    def get_queryset(self):
        return Call.objects.filter(tenant_id=_get_tenant_id(self.request))


class BillingAccountViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BillingAccountSerializer
    permission_classes = [IsSameTenant]

    def get_queryset(self):
        return BillingAccount.objects.filter(tenant_id=_get_tenant_id(self.request))

# ==========================================
# ROUTER
# ==========================================
router = DefaultRouter()
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'configs', AIConfigViewSet, basename='aiconfig')
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'calls', CallViewSet, basename='call')
router.register(r'billing', BillingAccountViewSet, basename='billingaccount')
