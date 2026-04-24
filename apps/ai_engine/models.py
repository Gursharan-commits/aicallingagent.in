from django.db import models

class AIConfig(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='ai_configs')
    name = models.CharField(max_length=255)
    version = models.IntegerField(default=1)
    graph_json = models.JSONField(help_text="Nodes, edges, and config properties for the execution engine")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} v{self.version}"
