import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant

User = get_user_model()

# Create a default tenant for admin
default_tenant, _ = Tenant.objects.get_or_create(
    name="Global Admin Tenant",
    defaults={"region": "IN", "pricing_tier": "enterprise"}
)

# Create admin user
if not User.objects.filter(username="admin").exists():
    admin = User.objects.create_superuser("admin", "admin@example.com", "admin", tenant=default_tenant, role="admin")
    print("Admin user created.")
else:
    print("Admin user already exists.")

# Create test_tenant1 tenant
tenant1, _ = Tenant.objects.get_or_create(
    name="Test Tenant 1",
    defaults={"region": "UK", "pricing_tier": "payg"}
)

# Create test_tenant1 user
if not User.objects.filter(username="test_tenant1").exists():
    tenant_user = User.objects.create_user("test_tenant1", "test@example.com", "test_tenant1", tenant=tenant1, role="admin")
    print("Test tenant user created.")
else:
    print("Test tenant user already exists.")
