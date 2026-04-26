from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0002_initial"),
        ("ai_engine", "0001_initial"),
    ]

    operations = [
        # Call — data_region + ai_config FK + ended_at
        migrations.AddField(
            model_name="call",
            name="data_region",
            field=models.CharField(
                blank=True,
                default="",
                help_text="AWS region where this call's data is stored.",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="call",
            name="ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="call",
            name="ai_config",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="calls",
                to="ai_engine.aiconfig",
                help_text="The pipeline config active when this call was initiated.",
            ),
        ),
        # Transcript — text_masked column for PII-safe export
        migrations.AddField(
            model_name="transcript",
            name="text_masked",
            field=models.TextField(
                blank=True,
                default="",
                help_text="PII-masked version of text, stored separately for safe export.",
            ),
            preserve_default=False,
        ),
    ]
