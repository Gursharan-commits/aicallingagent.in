from django.db import models


class ProviderCostRate(models.Model):
    """
    Stores what we pay each AI provider per unit consumed.
    Used by the shadow ledger to calculate provider_cost_cents.

    unit examples: 'per_second' (STT/TTS), 'per_1k_tokens' (LLM),
                   'per_character' (TTS character-based billing)
    """

    SERVICE_TYPE_CHOICES = [
        ("stt", "Speech-to-Text"),
        ("tts", "Text-to-Speech"),
        ("llm", "Language Model"),
        ("telephony", "Telephony / SIP"),
    ]

    provider = models.CharField(
        max_length=50,
        help_text="e.g. deepgram, cartesia, openai, gemini, sarvam, telnyx",
    )
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES)
    cost_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        help_text="Cost in USD per unit (e.g. 0.000059 per second for Deepgram Nova-3).",
    )
    unit = models.CharField(
        max_length=30,
        help_text="Unit descriptor: per_second | per_1k_tokens | per_character",
    )
    effective_from = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("provider", "service_type", "effective_from")]

    def __str__(self) -> str:
        return f"{self.provider}/{self.service_type} — {self.cost_per_unit}/{self.unit}"


class BillingAccount(models.Model):
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="billing_account",
    )
    balance_cents = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")

    def __str__(self) -> str:
        return f"{self.tenant.name} — {self.balance_cents} {self.currency}"


class Ledger(models.Model):
    """
    Shadow Ledger: records both what we CHARGE the tenant (retail)
    and what we PAY the provider (cost), enabling margin tracking.

    margin_cents = retail_charge_cents - provider_cost_cents
    """

    TYPE_CHOICES = [
        ("DEDUCTION", "Deduction"),       # call cost charged to tenant
        ("RECHARGE", "Recharge"),         # balance top-up
        ("ADJUSTMENT", "Adjustment"),     # manual credit / debit
    ]

    account = models.ForeignKey(
        BillingAccount,
        on_delete=models.CASCADE,
        related_name="ledger_entries",
    )
    call = models.ForeignKey(
        "calls.Call",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries",
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    # ── Shadow Ledger columns ─────────────────────────────────────────────────
    # What the tenant is charged (retail price).
    retail_charge_cents = models.BigIntegerField(
        default=0,
        help_text="Amount charged to the tenant's balance (cents).",
    )
    # What we pay our AI providers for this interval.
    provider_cost_cents = models.BigIntegerField(
        default=0,
        help_text="Aggregated provider cost for this billing interval (cents).",
    )
    # Provider cost breakdown — {provider: cost_cents} for auditability.
    provider_cost_breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text='e.g. {"deepgram": 5, "cartesia": 3, "openai": 12}',
    )

    # Legacy field kept for backwards compat; prefer retail_charge_cents.
    amount_cents = models.BigIntegerField(
        default=0,
        help_text="[Legacy] Kept for backwards compat. Use retail_charge_cents.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["call"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.type} retail={self.retail_charge_cents}¢ "
            f"cost={self.provider_cost_cents}¢ @ {self.created_at}"
        )

    @property
    def margin_cents(self) -> int:
        return self.retail_charge_cents - self.provider_cost_cents
