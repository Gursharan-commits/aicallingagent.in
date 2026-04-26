from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Extended user model with 4-tier RBAC.

    Tier hierarchy (highest → lowest privilege):
        super_admin   — Platform-level. Can manage all tenants.
        admin         — Tenant-level admin. Full access within their tenant.
        tenant_admin  — Manages agents and campaigns within their tenant.
        tenant_user   — Read-only / operational access within their tenant.
    """

    ROLE_CHOICES = [
        ("super_admin", "Super Admin"),
        ("admin", "Admin"),
        ("tenant_admin", "Tenant Admin"),
        ("tenant_user", "Tenant User"),
    ]

    # Null for super_admin who spans all tenants.
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="tenant_user")
    permissions = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"

    # ── Convenience helpers ───────────────────────────────────────────────────

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    @property
    def is_admin(self) -> bool:
        return self.role in ("super_admin", "admin")

    @property
    def is_tenant_admin(self) -> bool:
        return self.role in ("super_admin", "admin", "tenant_admin")
