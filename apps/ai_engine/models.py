from django.db import models


class AIConfig(models.Model):
    """
    Per-tenant AI pipeline configuration.

    graph_json defines the node/edge graph executed by GraphExecutor.
    Compliance fields control regulatory behaviour injected at runtime.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ai_configs",
    )
    name = models.CharField(max_length=255)
    version = models.IntegerField(default=1)
    graph_json = models.JSONField(
        help_text="Nodes, edges, and provider config for the execution engine."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Compliance ────────────────────────────────────────────────────────────
    ai_disclosure_enabled = models.BooleanField(
        default=False,
        help_text=(
            "When True the agent prepends the disclosure text to its first utterance. "
            "Required in many jurisdictions when an AI is indistinguishable from a human."
        ),
    )
    ai_disclosure_text = models.TextField(
        default="This call may be recorded and is handled by an AI assistant.",
        blank=True,
        help_text="Text prepended to the agent's first greeting when disclosure is enabled.",
    )
    compliance_flags = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Arbitrary compliance toggles, e.g. "
            '{"record_consent_required": true, "gdpr_mode": true}'
        ),
    )

    def __str__(self) -> str:
        return f"{self.name} v{self.version} (tenant={self.tenant_id})"


class AgentTool(models.Model):
    """
    A REST API tool that the AI agent can invoke at runtime.

    Defined by an admin in the dashboard, stored here, and dispatched by
    the APIToolNode in GraphExecutor when the LLM requests it.

    URL and body templates support {variable} placeholders that are resolved
    against GraphContext.variables at call time.

    Example:
        name        = "check_order_status"
        method      = "GET"
        url_template= "https://api.acme.com/orders/{order_id}"
        headers     = {"Authorization": "Bearer {api_key}"}
        body_template = {}
    """

    METHOD_CHOICES = [
        ("GET", "GET"),
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("PATCH", "PATCH"),
        ("DELETE", "DELETE"),
    ]

    ai_config = models.ForeignKey(
        AIConfig,
        on_delete=models.CASCADE,
        related_name="tools",
    )
    name = models.CharField(
        max_length=100,
        help_text="Snake_case identifier the LLM uses to call this tool.",
    )
    description = models.TextField(
        help_text="Plain-English description shown to the LLM for tool selection.",
    )
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="POST")
    url_template = models.CharField(
        max_length=1024,
        help_text="URL with optional {variable} placeholders.",
    )
    headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="HTTP headers dict. Values may use {variable} placeholders.",
    )
    body_template = models.JSONField(
        default=dict,
        blank=True,
        help_text="Request body template. Values may use {variable} placeholders.",
    )
    timeout_sec = models.IntegerField(default=10)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.name} [{self.method}] (config={self.ai_config_id})"
