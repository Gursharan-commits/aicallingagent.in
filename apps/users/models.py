from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('agent', 'Agent'),
    ]

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='users')
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='agent')
    permissions = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.username
