# AI Voice Agent Backend Architecture

This document outlines the architecture for a highly scalable, multi-tenant, event-driven AI Voice Agent platform powered by a dynamic Graph Execution Engine.

## 1. Django App Structure

The monolithic (but modular) Django codebase is structured around domains to ensure separation of concerns:

```text
backend/
├── config/                 # Django settings (base, local, prod), wsgi.py, asgi.py
├── apps/
│   ├── core/               # Shared utilities, base models, custom exceptions
│   ├── tenants/            # Tenant, Region routing, Tenant Settings
│   ├── users/              # Custom User model, JWT Auth, Role-based Permissions
│   ├── campaigns/          # Campaigns, Contacts, Scheduling
│   ├── calls/              # Call session, Transcripts, Interrupt events
│   ├── billing/            # BillingAccount, Ledger, Real-time deduction logic
│   ├── ai_engine/          # AIConfig (Graph JSON), GraphExecutor, NodeRunners
│   ├── analytics/          # ClickHouse syncing, aggregations, TurnMetrics
│   └── websockets/         # Django Channels consumers (frontend dashboard)
```

## 2. Core Models (Detailed)

```python
# tenants/models.py
class Tenant(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=10, choices=[('IN', 'India'), ('UK', 'United Kingdom')])
    pricing_tier = models.CharField(max_length=50) # e.g., 'enterprise', 'payg'
    is_active = models.BooleanField(default=True)

# users/models.py
class User(AbstractBaseUser):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=50, choices=[('admin', 'Admin'), ('agent', 'Agent')])
    permissions = models.JSONField(default=dict)

# ai_engine/models.py
class AIConfig(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    version = models.IntegerField(default=1)
    # The SOURCE OF TRUTH for execution
    graph_json = models.JSONField(help_text="Nodes, edges, and config properties")

# campaigns/models.py
class Campaign(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    ai_config = models.ForeignKey(AIConfig, on_delete=models.PROTECT)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50) # DRAFT, ACTIVE, PAUSED, COMPLETED

# calls/models.py
class Call(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    campaign = models.ForeignKey(Campaign, null=True, on_delete=models.SET_NULL)
    livekit_room_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=50) # QUEUED, IN_PROGRESS, HUMAN_TAKEOVER, COMPLETED, FAILED
    duration_sec = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    recording_url = models.URLField(null=True, blank=True)

class Transcript(models.Model):
    call = models.ForeignKey(Call, on_delete=models.CASCADE)
    role = models.CharField(max_length=10) # user, bot, system
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    latency_ms = models.IntegerField(null=True) # E2E latency if bot

# billing/models.py
class BillingAccount(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE)
    balance_cents = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3)

class Ledger(models.Model):
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE)
    call = models.ForeignKey(Call, null=True, on_delete=models.SET_NULL)
    amount_cents = models.BigIntegerField()
    type = models.CharField(max_length=20) # DEDUCTION, RECHARGE
```

## 3. Graph Execution Engine (The Core)

Instead of a static `pipeline.py`, the backend runs an asynchronous **GraphExecutor** that dynamically reads `AIConfig.graph_json`.

### Input JSON Structure (Graphify compatible execution graph)
```json
{
  "nodes": [
    { "id": "stt_1", "type": "STT", "provider": "deepgram", "config": {"language": "en-IN"} },
    { "id": "logic_1", "type": "LOGIC", "action": "check_sentiment" },
    { "id": "rag_1", "type": "RAG", "collection": "knowledge_base" },
    { "id": "llm_1", "type": "LLM", "provider": "gemini", "system_prompt": "You are a helpful agent" },
    { "id": "tts_1", "type": "TTS", "provider": "cartesia", "voice_id": "xxx-yyy" }
  ],
  "edges": [
    { "from": "stt_1", "to": "logic_1" },
    { "from": "logic_1", "to": "rag_1", "condition": "needs_info" },
    { "from": "rag_1", "to": "llm_1" },
    { "from": "llm_1", "to": "tts_1" }
  ]
}
```

### Execution Model
1. **Node Runners**: Each node type implements a standard interface `async def process(context: GraphContext)`.
2. **Context Passing**: A shared `GraphContext` carries `audio_stream`, `text_stream`, `call_state`, and `variables`.
3. **Streaming Pipelines**: The engine builds an `asyncio` task graph based on edges. For `STT -> LLM -> TTS`, it wires the async generators dynamically (STT yields chunks to LLM, LLM yields sentences to TTS).
4. **Dynamic Interrupts**: When `InterruptHandler` detects energy, the engine broadcasts an `INTERRUPT` signal to all executing nodes. `TTSNode` stops streaming, `LLMNode` cancels generation, and control returns to the `STTNode` wait loop.

## 4. Event System Architecture

The system uses **Redis Pub/Sub** (or Kafka for high throughput) to decouple the real-time audio pipeline from analytics and state management.

- `CALL_STARTED`: Emitted by the GraphExecutor. Bootstraps the Call record.
- `TRANSCRIPT_STREAM`: Emitted rapidly by `STTNode` (interim) and `LLMNode` (chunks). Used for dashboard UI.
- `AI_RESPONSE`: Finalized bot turn (async trigger to write to ClickHouse & Postgres).
- `HUMAN_TAKEOVER`: Control event. Immediately pauses GraphExecutor nodes.
- `CALL_ENDED`: Triggers final billing sync and recording fetch from S3.

**Async Workers (Celery/FastStream):**
- `LoggingWorker`: Batches events and writes them to ClickHouse for analytics and Postgres for standard CRUD.
- `RAGWorker`: Async updates to Vector DB when call insights are generated post-call.

## 5. WebSocket Flow & Call Control

Django Channels (Daphne) manages WebSockets connecting the Frontend Dashboard to the Backend.

1. Frontend connects to `wss://api.domain.com/ws/calls/{room_id}/`.
2. Channels Consumer subscribes to the Redis topic `call:{room_id}:events`.
3. The GraphExecutor (running as an isolated async process connected to LiveKit) emits `TRANSCRIPT_STREAM` to Redis.
4. The Channel Consumer forwards these streams to the Frontend to render live transcripts.
5. **Human Takeover**:
   - Frontend sends `{"action": "takeover"}` via WebSocket.
   - Channels publishes `CONTROL:HUMAN_TAKEOVER` to Redis.
   - GraphExecutor receives it, immediately halts `LLMNode` and `TTSNode`, and routes the human operator's audio from LiveKit to the user.

## 6. Billing Logic (Real-time)

To prevent fraudulent over-usage, billing tracks usage precisely:
1. **Rate Config**: Loaded from `Tenant.pricing_tier`.
2. **Real-time Checks**: A dedicated Celery Beat task runs every 5 seconds, scanning active `Call` sessions.
3. **Deduction**: It deducts `(rate / 60) * 5` from the `BillingAccount` in Redis (fast).
4. **Enforcement**: If `balance <= 0`, a `FORCE_END` event is sent to the GraphExecutor via Redis.
5. **Finalization**: On `CALL_ENDED`, Redis balance is atomically synced to the `Ledger` in PostgreSQL.

## 7. Multi-Region Compliance

To comply with local regulations (India vs UK):
- **Database Routing**: Django's Database Router inspects the request or tenant ID and routes writes to the respective Regional Database.
  - `db_in` -> AWS RDS Mumbai
  - `db_uk` -> AWS RDS London
- **Storage**: Audio recordings are uploaded to `s3://bucket-mumbai` or `s3://bucket-london` based on `Tenant.region`.
- **Compute Locality**: The GraphExecutor & LiveKit endpoints are deployed in region-specific clusters. Tenant A connects to `in.api.domain.com`, Tenant B to `uk.api.domain.com`.

## 8. Deployment Architecture

- **Load Balancer**: AWS ALB handling HTTP/HTTPS and WSS.
- **API & Channels**: Django + Daphne running on AWS ECS (Fargate).
- **Execution Engine**: Specialized isolated Python workers (non-Django HTTP) for the GraphExecutor and LiveKit integrations, optimized for long-running asyncio tasks.
- **State & Events**: AWS ElastiCache (Redis) for Pub/Sub, fast billing buffers, and WebSocket state.
- **Primary DB**: AWS Aurora PostgreSQL (Multi-region deployment).
- **Analytics DB**: ClickHouse Cloud (for sub-second query latency over millions of metrics/logs).
- **Vector DB**: Pinecone or Qdrant for RAG nodes, with namespaces per tenant.
