from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        # Expand role choices to 4-tier RBAC and change default
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("super_admin", "Super Admin"),
                    ("admin", "Admin"),
                    ("tenant_admin", "Tenant Admin"),
                    ("tenant_user", "Tenant User"),
                ],
                default="tenant_user",
                max_length=50,
            ),
        ),
        # tenant FK now nullable (super_admin spans all tenants)
        migrations.AlterField(
            model_name="user",
            name="tenant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="users",
                to="tenants.tenant",
            ),
        ),
    ]
