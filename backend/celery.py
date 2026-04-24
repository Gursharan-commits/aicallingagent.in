import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# Load config from Django settings, using the CELERY_ namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover tasks in all installed apps
app.autodiscover_tasks()

# ── Beat Schedule ─────────────────────────────────────────────
app.conf.beat_schedule = {
    'realtime-billing-every-30s': {
        'task': 'apps.billing.tasks.calculate_realtime_billing',
        'schedule': 30.0,  # seconds
    },
}
app.conf.timezone = 'UTC'
