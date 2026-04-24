from django.db import models

class BillingAccount(models.Model):
    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='billing_account')
    balance_cents = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default='USD')

    def __str__(self):
        return f"{self.tenant.name} - {self.balance_cents} {self.currency}"

class Ledger(models.Model):
    TYPE_CHOICES = [
        ('DEDUCTION', 'Deduction'),
        ('RECHARGE', 'Recharge'),
    ]

    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name='ledger_entries')
    call = models.ForeignKey('calls.Call', null=True, blank=True, on_delete=models.SET_NULL)
    amount_cents = models.BigIntegerField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} of {self.amount_cents} on {self.created_at}"
