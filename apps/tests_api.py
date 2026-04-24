import json
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant
from apps.ai_engine.models import AIConfig
from apps.campaigns.models import Campaign

User = get_user_model()

SAMPLE_GRAPH = {
    "nodes": [
        {"id": "stt_1", "type": "STT", "config": {"provider": "deepgram"}},
        {"id": "llm_1", "type": "LLM", "config": {"provider": "gemini"}},
    ],
    "edges": [{"from": "stt_1", "to": "llm_1"}]
}

def make_authenticated_client(tenant):
    """Helper: return an APIClient force-authenticated as an admin user of this tenant."""
    user = User.objects.create_user(
        username=f"admin_{tenant.id}",
        email=f"admin_{tenant.id}@test.com",
        password="testpass123",
        tenant=tenant,
        role="admin",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user

class TenantAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme Corp", region="IN", pricing_tier="enterprise")
        self.client, self.user = make_authenticated_client(self.tenant)

    def test_list_tenants(self):
        """GET /api/v1/tenants/ returns the authenticated user's own tenant."""
        response = self.client.get('/api/v1/tenants/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], "Acme Corp")

    def test_unauthenticated_is_rejected(self):
        """Unauthenticated requests must return 401."""
        anon = APIClient()
        response = anon.get('/api/v1/tenants/')
        self.assertEqual(response.status_code, 401)


class AIConfigAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme Corp", region="IN", pricing_tier="enterprise")
        self.client, self.user = make_authenticated_client(self.tenant)

    def test_create_ai_config_with_graph_json(self):
        """POST /api/v1/configs/ saves a graph and returns 201."""
        payload = {
            "name": "Standard Voice Bot",
            "graph_json": SAMPLE_GRAPH
        }
        response = self.client.post('/api/v1/configs/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        saved = AIConfig.objects.get(tenant=self.tenant)
        self.assertEqual(saved.name, "Standard Voice Bot")

    def test_graph_json_is_persisted_correctly(self):
        """Ensure graph_json roundtrips through DB without corruption."""
        config = AIConfig.objects.create(
            tenant=self.tenant,
            name="Pipeline Test",
            graph_json=SAMPLE_GRAPH
        )
        config.refresh_from_db()
        self.assertEqual(config.graph_json['nodes'][0]['id'], 'stt_1')
        self.assertEqual(len(config.graph_json['edges']), 1)

    def test_cross_tenant_isolation(self):
        """User from tenant A must not see configs from tenant B."""
        other_tenant = Tenant.objects.create(name="Evil Corp", region="UK", pricing_tier="payg")
        AIConfig.objects.create(tenant=other_tenant, name="Enemy Config", graph_json=SAMPLE_GRAPH)
        response = self.client.get('/api/v1/configs/')
        self.assertEqual(response.status_code, 200)
        # Should return empty — our tenant has no configs yet
        self.assertEqual(len(response.json()), 0)


class CampaignAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme Corp", region="IN", pricing_tier="enterprise")
        self.client, self.user = make_authenticated_client(self.tenant)
        self.config = AIConfig.objects.create(
            tenant=self.tenant,
            name="Campaign Config",
            graph_json=SAMPLE_GRAPH
        )

    def test_create_campaign(self):
        """POST /api/v1/campaigns/ creates a campaign linked to a config."""
        payload = {
            "ai_config": self.config.id,
            "name": "Q2 Outreach"
        }
        response = self.client.post('/api/v1/campaigns/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Campaign.objects.count(), 1)
        self.assertEqual(Campaign.objects.first().name, "Q2 Outreach")

    def test_list_campaigns(self):
        """GET /api/v1/campaigns/ returns only this tenant's campaigns."""
        Campaign.objects.create(tenant=self.tenant, ai_config=self.config, name="Test Camp")
        response = self.client.get('/api/v1/campaigns/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

