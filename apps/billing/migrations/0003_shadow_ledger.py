from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_initial"),
        ("calls", "0002_initial"),
    ]

    operations = [
        # ── ProviderCostRate table ────────────────────────────────────────────
        migrations.CreateModel(
            name="ProviderCostRate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=50, help_text="e.g. deepgram, cartesia, openai, gemini, sarvam, telnyx")),
                ("service_type", models.CharField(
                    choices=[("stt", "Speech-to-Text"), ("tts", "Text-to-Speech"), ("llm", "Language Model"), ("telephony", "Telephony / SIP")],
                    max_length=20,
                )),
                ("cost_per_unit", models.DecimalField(
                    decimal_places=6, max_digits=12,
                    help_text="Cost in USD per unit.",
                )),
                ("unit", models.CharField(max_length=30, help_text="per_second | per_1k_tokens | per_character")),
                ("effective_from", models.DateField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"unique_together": {("provider", "service_type", "effective_from")}},
        ),
        # ── Shadow ledger columns on Ledger ───────────────────────────────────
        migrations.AddField(
            model_name="ledger",
            name="retail_charge_cents",
            field=models.BigIntegerField(default=0, help_text="Amount charged to the tenant's balance (cents)."),
        ),
        migrations.AddField(
            model_name="ledger",
            name="provider_cost_cents",
            field=models.BigIntegerField(default=0, help_text="Aggregated provider cost for this billing interval (cents)."),
        ),
        migrations.AddField(
            model_name="ledger",
            name="provider_cost_breakdown",
            field=models.JSONField(blank=True, default=dict, help_text='e.g. {"deepgram": 5, "cartesia": 3, "openai": 12}'),
        ),
        migrations.AddField(
            model_name="ledger",
            name="notes",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        # Rename amount_cents to keep it but mark it legacy
        migrations.AlterField(
            model_name="ledger",
            name="amount_cents",
            field=models.BigIntegerField(default=0, help_text="[Legacy] Kept for backwards compat. Use retail_charge_cents."),
        ),
        # Add index on account+created_at for billing cycle query performance
        migrations.AddIndex(
            model_name="ledger",
            index=models.Index(fields=["account", "created_at"], name="ledger_account_created_idx"),
        ),
        migrations.AddIndex(
            model_name="ledger",
            index=models.Index(fields=["call"], name="ledger_call_idx"),
        ),
        # Add ADJUSTMENT to type choices
        migrations.AlterField(
            model_name="ledger",
            name="type",
            field=models.CharField(
                choices=[("DEDUCTION", "Deduction"), ("RECHARGE", "Recharge"), ("ADJUSTMENT", "Adjustment")],
                max_length=20,
            ),
        ),
    ]
