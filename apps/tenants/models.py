from django.db import models

class Tenant(models.Model):
    REGION_CHOICES = [
        ('IN', 'India'),
        ('UK', 'United Kingdom'),
    ]

    name = models.CharField(max_length=255)
    region = models.CharField(max_length=10, choices=REGION_CHOICES)
    pricing_tier = models.CharField(max_length=50) # e.g., 'enterprise', 'payg'
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.region})"
