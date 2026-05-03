import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "kyros",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.inventory_snapshot",
        "app.tasks.performance_snapshot",
        "app.tasks.alert_generation",
        "app.tasks.uploads",
        "app.tasks.allocation",
        "app.tasks.llm_refresh",
    ],
)

celery_app.conf.timezone = "Asia/Kolkata"

# Cache-flush cadence for the Groq client. Default 10 min; override via
# GROQ_KEY_REFRESH_MINUTES env var.
_groq_refresh_min = max(1, int(os.environ.get("GROQ_KEY_REFRESH_MINUTES", "10")))

celery_app.conf.beat_schedule = {
    "build-inventory-snapshots-daily": {
        "task": "app.tasks.inventory_snapshot.build_inventory_snapshots",
        "schedule": crontab(hour=1, minute=0),
    },
    "build-performance-snapshots-daily": {
        "task": "app.tasks.performance_snapshot.build_performance_snapshots",
        "schedule": crontab(hour=2, minute=0),
    },
    "generate-alerts-daily": {
        "task": "app.tasks.alert_generation.generate_alerts_task",
        "schedule": crontab(hour=6, minute=0),
    },
    "refresh-groq-keys": {
        "task": "app.tasks.llm_refresh.refresh_groq_keys",
        "schedule": timedelta(minutes=_groq_refresh_min),
    },
}
