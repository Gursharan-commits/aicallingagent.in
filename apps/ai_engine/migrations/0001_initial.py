from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("version", models.IntegerField(default=1)),
                ("graph_json", models.JSONField(help_text="Nodes, edges, and provider config for the execution engine.")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                # Compliance fields
                ("ai_disclosure_enabled", models.BooleanField(
                    default=False,
                    help_text="When True the agent prepends the disclosure text to its first utterance.",
                )),
                ("ai_disclosure_text", models.TextField(
                    blank=True,
                    default="This call may be recorded and is handled by an AI assistant.",
                    help_text="Text prepended to the agent's first greeting when disclosure is enabled.",
                )),
                ("compliance_flags", models.JSONField(
                    blank=True,
                    default=dict,
                    help_text='Arbitrary compliance toggles, e.g. {"record_consent_required": true}',
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="ai_configs",
                    to="tenants.tenant",
                )),
            ],
        ),
        migrations.CreateModel(
            name="AgentTool",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Snake_case identifier the LLM uses to call this tool.", max_length=100)),
                ("description", models.TextField(help_text="Plain-English description shown to the LLM for tool selection.")),
                ("method", models.CharField(
                    choices=[("GET", "GET"), ("POST", "POST"), ("PUT", "PUT"), ("PATCH", "PATCH"), ("DELETE", "DELETE")],
                    default="POST",
                    max_length=10,
                )),
                ("url_template", models.CharField(help_text="URL with optional {variable} placeholders.", max_length=1024)),
                ("headers", models.JSONField(blank=True, default=dict, help_text="HTTP headers dict. Values may use {variable} placeholders.")),
                ("body_template", models.JSONField(blank=True, default=dict, help_text="Request body template. Values may use {variable} placeholders.")),
                ("timeout_sec", models.IntegerField(default=10)),
                ("is_active", models.BooleanField(default=True)),
                ("ai_config", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="tools",
                    to="ai_engine.aiconfig",
                )),
            ],
        ),
    ]
