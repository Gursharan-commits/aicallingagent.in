"""
Billing tasks — real-time deductions and shadow ledger.

Celery Beat schedule (add to CELERY_BEAT_SCHEDULE in settings.py):
    'billing-cycle': {
        'task': 'apps.billing.tasks.calculate_realtime_billing',
        'schedule': 10.0,   # every 10 seconds
    }
"""

import logging
from decimal import Decimal

from celery import shared_task
from django.db import transaction
from django.utils.timezone import now

from apps.calls.models import Call
from apps.billing.models import BillingAccount, Ledger, ProviderCostRate

logger = logging.getLogger(__name__)

# ── Retail pricing ────────────────────────────────────────────────────────────
# Cents charged to the tenant per second of active call.
# These are the *retail* rates; provider costs come from ProviderCostRate table.
RETAIL_CENTS_PER_SECOND = Decimal("5")  # $0.05/min  → 0.0833¢/s → round to 5¢/s

# ── Default provider cost estimates (fallback when no ProviderCostRate row) ───
# Based on public pricing; update ProviderCostRate rows for real accuracy.
_PROVIDER_DEFAULTS_CENTS_PER_SECOND: dict[str, Decimal] = {
    "deepgram": Decimal("0.5"),   # Nova-3 ~$0.0043/min
    "cartesia": Decimal("0.4"),   # per character; approximated as per-second
    "openai":   Decimal("1.5"),   # GPT-4o-mini tokens; approximated
    "gemini":   Decimal("0.3"),   # Gemini 2.0 Flash; approximated
    "sarvam":   Decimal("0.4"),
}


def _get_provider_cost_per_second(provider: str, service_type: str) -> Decimal:
    """
    Look up provider cost from the ProviderCostRate table.
    Falls back to hardcoded defaults if no active rate is found.
    """
    rate = (
        ProviderCostRate.objects.filter(
            provider=provider,
            service_type=service_type,
            is_active=True,
        )
        .order_by("-effective_from")
        .first()
    )
    if rate:
        if rate.unit == "per_second":
            return Decimal(str(rate.cost_per_unit)) * 100  # USD → cents
        # per_1k_tokens or per_character: convert approximate to per-second
        # You'd refine this with actual usage counters in production.
        return Decimal(str(rate.cost_per_unit)) * 100
    return _PROVIDER_DEFAULTS_CENTS_PER_SECOND.get(provider, Decimal("1"))


def _calculate_provider_cost_breakdown(
    call: "Call", billed_seconds: int
) -> tuple[int, dict[str, int]]:
    """
    Compute total provider cost (cents) and per-provider breakdown
    for a billing interval.

    Reads provider selection from call.ai_config.graph_json so it reflects
    whatever providers were actually configured for this call.
    """
    breakdown: dict[str, int] = {}
    total = Decimal("0")

    providers_used: dict[str, str] = {}  # {provider: service_type}

    if call.ai_config_id:
        try:
            graph = call.ai_config.graph_json
            for node in graph.get("nodes", []):
                cfg = node.get("config", {})
                provider = cfg.get("provider", "").lower()
                node_type = node.get("type", "").upper()
                if not provider:
                    continue
                svc = {"STT": "stt", "TTS": "tts", "LLM": "llm"}.get(node_type)
                if svc:
                    providers_used[provider] = svc
        except Exception as exc:
            logger.warning("Could not parse graph_json for call %s: %s", call.id, exc)

    if not providers_used:
        # Fallback: assume default stack
        providers_used = {"deepgram": "stt", "cartesia": "tts", "gemini": "llm"}

    for provider, svc in providers_used.items():
        cost = _get_provider_cost_per_second(provider, svc) * billed_seconds
        cents = int(cost)
        breakdown[provider] = cents
        total += cost

    return int(total), breakdown


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def calculate_realtime_billing(self):
    """
    Scans all IN_PROGRESS calls, deducts retail cost from tenant balance,
    logs a shadow-ledger entry with provider cost breakdown, and terminates
    calls that exceed their credit.

    Shadow ledger per entry:
        retail_charge_cents  — what the tenant pays us
        provider_cost_cents  — what we pay providers  (margin = retail - cost)
        provider_cost_breakdown — per-provider split
    """
    logger.info("Billing cycle started.")
    BILLED_SECONDS = 10
    retail_per_interval = int(RETAIL_CENTS_PER_SECOND * BILLED_SECONDS)

    active_calls = Call.objects.filter(status="IN_PROGRESS").select_related(
        "tenant", "ai_config"
    )

    for call in active_calls:
        try:
            with transaction.atomic():
                account = BillingAccount.objects.select_for_update().get(
                    tenant_id=call.tenant_id
                )

                provider_cost, breakdown = _calculate_provider_cost_breakdown(
                    call, BILLED_SECONDS
                )

                if account.balance_cents >= retail_per_interval:
                    account.balance_cents -= retail_per_interval
                    account.save()

                    Ledger.objects.create(
                        account=account,
                        call=call,
                        type="DEDUCTION",
                        retail_charge_cents=retail_per_interval,
                        provider_cost_cents=provider_cost,
                        provider_cost_breakdown=breakdown,
                        amount_cents=retail_per_interval,  # legacy compat
                        notes=f"Interval {BILLED_SECONDS}s",
                    )
                    logger.debug(
                        "Billed call %s: retail=%d¢ cost=%d¢ margin=%d¢",
                        call.id,
                        retail_per_interval,
                        provider_cost,
                        retail_per_interval - provider_cost,
                    )
                else:
                    logger.warning(
                        "Tenant %s out of credits — terminating call %s",
                        call.tenant_id,
                        call.id,
                    )
                    call.status = "COMPLETED"
                    call.ended_at = now()
                    call.save()

                    # Fire termination event to the Redis channel so
                    # TelephonyBridge disconnects the LiveKit room.
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync

                    channel_layer = get_channel_layer()
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            f"call_{call.livekit_room_id}",
                            {"type": "control_event", "event": "OUT_OF_CREDITS"},
                        )

        except Exception as exc:
            logger.error("Billing failed for call %s: %s", call.id, exc)
            raise self.retry(exc=exc)

    logger.info("Billing cycle complete. Processed %d calls.", active_calls.count())


@shared_task
def record_call_end_ledger(call_id: int) -> None:
    """
    Called once when a call ends (via signal or webhook).
    Writes a final shadow-ledger summary entry with full-call provider cost.
    """
    try:
        call = Call.objects.select_related("tenant", "ai_config").get(pk=call_id)
        account = BillingAccount.objects.get(tenant_id=call.tenant_id)

        provider_cost, breakdown = _calculate_provider_cost_breakdown(
            call, call.duration_sec or 0
        )

        Ledger.objects.create(
            account=account,
            call=call,
            type="ADJUSTMENT",
            retail_charge_cents=0,
            provider_cost_cents=provider_cost,
            provider_cost_breakdown=breakdown,
            amount_cents=0,
            notes="End-of-call provider cost summary",
        )
        logger.info("End-of-call ledger written for call %s", call_id)
    except Exception as exc:
        logger.error("record_call_end_ledger failed for call %s: %s", call_id, exc)
