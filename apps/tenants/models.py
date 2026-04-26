from django.db import models


class Tenant(models.Model):
    REGION_CHOICES = [
        ("IN", "India"),
        ("UK", "United Kingdom"),
    ]

    # Cloud region for data residency compliance.
    # IN tenants → ap-south-1 (Mumbai)
    # UK tenants → eu-west-2 (London)
    CLOUD_REGION_MAP = {
        "IN": "ap-south-1",
        "UK": "eu-west-2",
    }

    name = models.CharField(max_length=255)
    region = models.CharField(max_length=10, choices=REGION_CHOICES)
    pricing_tier = models.CharField(max_length=50)   # e.g. 'enterprise', 'payg'
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.region})"

    @property
    def cloud_region(self) -> str:
        """AWS region identifier for data residency enforcement."""
        return self.CLOUD_REGION_MAP.get(self.region, "us-east-1")
