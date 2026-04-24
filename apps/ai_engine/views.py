from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import AIConfig
from apps.tenants.models import Tenant

@method_decorator(csrf_exempt, name='dispatch')
class UpdateGraphConfigView(APIView):
    """
    POST endpoint to overwrite the AIConfig.graph_json field.
    Expects JSON body: { "nodes": [...], "edges": [...] }
    """
    def post(self, request, *args, **kwargs):
        # Retrieve or create a default config for Tenant 1
        tenant, _ = Tenant.objects.get_or_create(id=1, defaults={"name": "Default Tenant"})
        config, created = AIConfig.objects.get_or_create(
            tenant=tenant, 
            name="Default Pipeline", 
            defaults={"version": 1, "graph_json": {"nodes": [], "edges": []}}
        )

        graph_json = request.data.get('graph_json')
        if not graph_json:
            return Response({"error": "graph_json is required"}, status=status.HTTP_400_BAD_REQUEST)

        config.graph_json = graph_json
        config.save()

        return Response({
            "message": "Graph configuration updated successfully",
            "config_id": config.id,
            "graph_json": config.graph_json
        })

    def get(self, request, *args, **kwargs):
        tenant, _ = Tenant.objects.get_or_create(id=1, defaults={"name": "Default Tenant"})
        config, created = AIConfig.objects.get_or_create(
            tenant=tenant, 
            name="Default Pipeline", 
            defaults={
                "version": 1, 
                "graph_json": {
                    "nodes": [
                        {"id": "stt_1", "type": "STT", "position": {"x": 100, "y": 100}, "data": {"label": "Deepgram STT"}, "config": {"provider": "deepgram"}},
                        {"id": "llm_1", "type": "LLM", "position": {"x": 400, "y": 100}, "data": {"label": "GPT-4 Engine"}, "config": {"provider": "openai"}},
                        {"id": "tts_1", "type": "TTS", "position": {"x": 700, "y": 100}, "data": {"label": "Cartesia TTS"}, "config": {"provider": "cartesia"}}
                    ],
                    "edges": [
                        {"id": "e1", "source": "stt_1", "target": "llm_1", "from": "stt_1", "to": "llm_1"},
                        {"id": "e2", "source": "llm_1", "target": "tts_1", "from": "llm_1", "to": "tts_1"}
                    ]
                }
            }
        )
        return Response(config.graph_json)
