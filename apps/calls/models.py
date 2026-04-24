from django.db import models

class Call(models.Model):
    STATUS_CHOICES = [
        ('QUEUED', 'Queued'),
        ('RINGING', 'Ringing'),
        ('IN_PROGRESS', 'In Progress'),
        ('HUMAN_TAKEOVER', 'Human Takeover'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='calls')
    campaign = models.ForeignKey('campaigns.Campaign', null=True, blank=True, on_delete=models.SET_NULL, related_name='calls')
    livekit_room_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='QUEUED')
    duration_sec = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    recording_url = models.URLField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Call {self.id} ({self.status})"

class Transcript(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('bot', 'Bot'),
        ('system', 'System'),
    ]

    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name='transcripts')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    latency_ms = models.IntegerField(null=True, blank=True, help_text="End-to-end latency if bot")

    def __str__(self):
        return f"[{self.role}] {self.text[:50]}"
