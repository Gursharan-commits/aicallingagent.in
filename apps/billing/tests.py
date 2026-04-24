from django.test import TestCase
from apps.tenants.models import Tenant
from apps.billing.models import BillingAccount, Ledger
from apps.calls.models import Call
from apps.billing.tasks import calculate_realtime_billing

class BillingEngineTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant", region="IN", pricing_tier="payg")
        self.account = BillingAccount.objects.create(tenant=self.tenant, balance_cents=100)
        self.call = Call.objects.create(
            tenant=self.tenant,
            livekit_room_id="call_test_1",
            status="IN_PROGRESS"
        )
        
    def test_calculate_realtime_billing_deducts_balance(self):
        """Test that the periodic task deducts money from the ledger."""
        calculate_realtime_billing()
        
        self.account.refresh_from_db()
        # 100 cents - (10 sec * 5 cents) = 50 cents
        self.assertEqual(self.account.balance_cents, 50)
        
        # Ledger should be created
        self.assertTrue(Ledger.objects.filter(account=self.account).exists())
        self.assertEqual(Ledger.objects.get(account=self.account).amount_cents, 50)

    def test_calculate_realtime_billing_terminates_call(self):
        """Test that a call is terminated if balance is too low."""
        self.account.balance_cents = 4 # Cost per cycle is 50 cents
        self.account.save()
        
        calculate_realtime_billing()
        
        self.call.refresh_from_db()
        self.account.refresh_from_db()
        
        # Call MUST be terminated
        self.assertEqual(self.call.status, "COMPLETED")
        # Balance should remain untouched as call was terminated due to lack of funds
        self.assertEqual(self.account.balance_cents, 4)
