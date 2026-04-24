from celery import shared_task
from django.db import transaction
from django.utils.timezone import now
from apps.calls.models import Call
from apps.billing.models import BillingAccount, Ledger
import logging

logger = logging.getLogger(__name__)

# This task should be scheduled to run every 10-30 seconds via Celery Beat
@shared_task
def calculate_realtime_billing():
    """
    Scans all 'IN_PROGRESS' calls, calculates the duration since the last billing cycle,
    deducts the cost from the tenant's ledger, and triggers a termination event if
    the balance drops below zero.
    """
    logger.info("Running real-time billing cycle...")
    
    # Cost per second in cents
    COST_PER_SECOND_CENTS = 5  

    # Fetch all active calls
    active_calls = Call.objects.filter(status='IN_PROGRESS')

    for call in active_calls:
        try:
            with transaction.atomic():
                # Lock the billing account row to prevent race conditions
                account = BillingAccount.objects.select_for_update().get(tenant_id=call.tenant_id)
                
                # Calculate time elapsed since last deduction
                # If we haven't billed yet, bill from start_time
                # For simplicity in this skeleton, we assume we bill every 10 seconds flat
                billed_seconds = 10 
                cost_cents = billed_seconds * COST_PER_SECOND_CENTS
                
                if account.balance_cents >= cost_cents:
                    account.balance_cents -= cost_cents
                    account.save()
                    
                    # Record the ledger entry
                    Ledger.objects.create(
                        account=account,
                        type='DEDUCTION',
                        amount_cents=cost_cents,
                        call=call
                    )
                else:
                    logger.warning(f"Tenant {call.tenant_id} out of credits. Terminating call {call.id}")
                    # Zero balance! Terminate the call
                    call.status = 'COMPLETED'
                    call.end_time = now()
                    call.save()
                    
                    # TODO: Fire an event to Redis so the TelephonyBridge disconnects the LiveKit room instantly
                    # channel_layer = get_channel_layer()
                    # async_to_sync(channel_layer.group_send)(f"call_{call.id}", {"type": "control_event", "event": "OUT_OF_CREDITS"})

        except Exception as e:
            logger.error(f"Failed to process billing for call {call.id}: {str(e)}")

