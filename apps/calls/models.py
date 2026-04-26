import re
from django.db import models
from apps.calls.pii import mask_pii


class Call(models.Model):
    STATUS_CHOICES = [
        ("QUEUED", "Queued"),
        ("RINGING", "Ringing"),
        ("IN_PROGRESS", "In Progress"),
        ("HUMAN_TAKEOVER", "Human Takeover"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="calls"
    )
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="calls",
    )
    ai_config = models.ForeignKey(
        "ai_engine.AIConfig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="calls",
        help_text="The pipeline config active when this call was initiated.",
    )
    livekit_room_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="QUEUED")
    duration_sec = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    recording_url = models.URLField(null=True, blank=True)

    # ── Data residency tagging ────────────────────────────────────────────────
    # Mirrors tenant.cloud_region at creation time so records can be filtered
    # for regulatory reporting without joining through to Tenant.
    data_region = models.CharField(
        max_length=20,
        blank=True,
        help_text="AWS region where this call's data is stored (e.g. ap-south-1).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Auto-tag data_region from tenant on first save.
        if not self.data_region and self.tenant_id:
            try:
                self.data_region = self.tenant.cloud_region
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Call {self.id} ({self.status})"


class Transcript(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("bot", "Bot"),
        ("system", "System"),
    ]

    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="transcripts")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    text = models.TextField()
    text_masked = models.TextField(
        blank=True,
        help_text="PII-masked version of text, stored separately for safe export.",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    latency_ms = models.IntegerField(
        null=True, blank=True, help_text="End-to-end latency if bot turn."
    )

    def save(self, *args, **kwargs):
        # Always regenerate the masked copy before persisting.
        self.text_masked = mask_pii(self.text)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[{self.role}] {self.text[:50]}"
