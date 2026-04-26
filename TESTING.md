# Testing Guide — Voice AI Platform

Work through each section in order. Steps 1–3 are setup; steps 4–9 test each
implemented feature. Every curl command assumes you're in the project root.

---

## 1. Prerequisites

```
Python 3.11+    pip    Redis    (Postgres optional — SQLite used by default)
```

### 1.1 Install dependencies

```powershell
# Create + activate venv (skip if already done)
python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 1.2 Start Redis (required for Django Channels + Celery)

```powershell
# Option A — Docker (recommended)
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Option B — Windows native (if installed)
redis-server
```

Verify: `redis-cli ping` should return `PONG`.

---

## 2. Environment setup

Copy the template and fill in at least the keys marked REQUIRED:

```powershell
Copy-Item .env.example .env
```

Minimum `.env` for local testing (SQLite mode — no Postgres needed):

```ini
# ── Django ───────────────────────────────────────────────────
DJANGO_SECRET_KEY=local-test-secret-key-change-in-prod
DJANGO_DEBUG=True

# ── AI Providers (REQUIRED for voice pipeline tests) ─────────
DEEPGRAM_API_KEY=your_key
GEMINI_API_KEY=your_key
CARTESIA_API_KEY=your_key
OPENAI_API_KEY=your_key       # only needed as LLM/TTS fallback

# ── Redis ─────────────────────────────────────────────────────
REDIS_URL=redis://127.0.0.1:6379/0

# Leave DB_*_HOST vars EMPTY to use SQLite (default for local dev)
```

---

## 3. Database setup

```powershell
# Run all migrations (creates SQLite files on first run)
python manage.py migrate
python manage.py migrate --database=india_db
python manage.py migrate --database=uk_db

# Create a super-admin user
python manage.py shell -c "
from apps.tenants.models import Tenant
from apps.users.models import User

# 1. Create two tenants
t_in = Tenant.objects.create(name='Acme India', region='IN', pricing_tier='payg')
t_uk = Tenant.objects.create(name='Acme UK',    region='UK', pricing_tier='enterprise')
print(f'Tenants: IN={t_in.id}  UK={t_uk.id}')

# 2. Create users for each tier
User.objects.create_superuser('superadmin', 'sa@acme.com', 'Test1234!', role='super_admin')
User.objects.create_user('admin_in',   'admin@acme.in',  'Test1234!', tenant=t_in, role='admin')
User.objects.create_user('tadmin_in',  'ta@acme.in',     'Test1234!', tenant=t_in, role='tenant_admin')
User.objects.create_user('tuser_in',   'tu@acme.in',     'Test1234!', tenant=t_in, role='tenant_user')
User.objects.create_user('admin_uk',   'admin@acme.uk',  'Test1234!', tenant=t_uk, role='admin')
print('Users created')

# 3. Billing accounts
from apps.billing.models import BillingAccount
BillingAccount.objects.create(tenant=t_in, balance_cents=100000)  # \$1000
BillingAccount.objects.create(tenant=t_uk, balance_cents=50000)
print('Billing accounts created')
"
```

---

## 4. Start the server

```powershell
# Terminal 1 — Django/Daphne ASGI server
python manage.py runserver 8000

# Terminal 2 — Celery worker (for billing tasks)
celery -A backend worker -l info

# Terminal 3 — Celery Beat (scheduler)
celery -A backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

You should see:
```
System check identified no issues.
Daphne listening on 127.0.0.1:8000
```

---

## 5. Test: Authentication & 4-Tier RBAC

### 5.1 Login — get JWT tokens

```powershell
# India admin
$r = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/auth/login/" `
  -ContentType "application/json" `
  -Body '{"username":"admin_in","password":"Test1234!"}'
$TOKEN_IN = $r.access
echo "India token: $TOKEN_IN"

# UK admin
$r2 = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/auth/login/" `
  -ContentType "application/json" `
  -Body '{"username":"admin_uk","password":"Test1234!"}'
$TOKEN_UK = $r2.access
echo "UK token: $TOKEN_UK"
```

### 5.2 Decode the JWT — verify claims

```powershell
python -c "
import base64, json, sys
token = '$TOKEN_IN'
payload = token.split('.')[1]
payload += '=' * (-len(payload) % 4)
print(json.dumps(json.loads(base64.urlsafe_b64decode(payload)), indent=2))
"
```

**Expected claims:**
```json
{
  "tenant_id": 1,
  "role": "admin",
  "email": "admin@acme.in",
  "cloud_region": "ap-south-1"
}
```

### 5.3 Tenant isolation — cross-tenant request should be blocked

```powershell
# India token trying to read UK tenant — should return empty list (not 403, filtered)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/tenants/" `
  -Headers @{Authorization="Bearer $TOKEN_UK"} | ConvertTo-Json

# Super admin can see all
$r3 = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/auth/login/" `
  -ContentType "application/json" `
  -Body '{"username":"superadmin","password":"Test1234!"}'
$TOKEN_SA = $r3.access
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/tenants/" `
  -Headers @{Authorization="Bearer $TOKEN_SA"} | ConvertTo-Json
```

✅ **Pass criteria:** India token sees only India tenant. Super admin sees both.

---

## 6. Test: Dynamic Configuration (Task 2)

### 6.1 Create an AIConfig via API

```powershell
$GRAPH = @'
{
  "name": "India Sales Bot",
  "is_active": true,
  "ai_disclosure_enabled": false,
  "ai_disclosure_text": "",
  "graph_json": {
    "nodes": [
      {"id":"stt_1","type":"STT","config":{"provider":"deepgram","language":"en-IN"}},
      {"id":"llm_1","type":"LLM","config":{"provider":"gemini","system_prompt":"You are a helpful sales assistant.","max_tokens":200}},
      {"id":"tts_1","type":"TTS","config":{"provider":"cartesia","language":"en"}}
    ],
    "edges":[
      {"from":"stt_1","to":"llm_1"},
      {"from":"llm_1","to":"tts_1"}
    ]
  }
}
'@

$config = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/configs/" `
  -Headers @{Authorization="Bearer $TOKEN_IN"; "Content-Type"="application/json"} `
  -Body $GRAPH

$CONFIG_ID = $config.id
echo "Created AIConfig id=$CONFIG_ID"
```

### 6.2 Switch provider — change LLM to OpenAI (no code change needed)

```powershell
$GRAPH_OPENAI = @'
{
  "name": "India Sales Bot",
  "is_active": true,
  "ai_disclosure_enabled": false,
  "ai_disclosure_text": "",
  "graph_json": {
    "nodes": [
      {"id":"stt_1","type":"STT","config":{"provider":"deepgram","language":"en-IN"}},
      {"id":"llm_1","type":"LLM","config":{"provider":"openai","model":"gpt-4o-mini","system_prompt":"You are a helpful sales assistant.","max_tokens":200}},
      {"id":"tts_1","type":"TTS","config":{"provider":"cartesia","language":"en"}}
    ],
    "edges":[
      {"from":"stt_1","to":"llm_1"},
      {"from":"llm_1","to":"tts_1"}
    ]
  }
}
'@

Invoke-RestMethod -Method Put -Uri "http://localhost:8000/api/v1/configs/$CONFIG_ID/" `
  -Headers @{Authorization="Bearer $TOKEN_IN"; "Content-Type"="application/json"} `
  -Body $GRAPH_OPENAI | ConvertTo-Json
```

✅ **Pass criteria:** Config saved. The worker will pick up the new provider next call — no restart required.

---

## 7. Test: Compliance Layer — AI Disclosure (Task 4)

### 7.1 Enable disclosure on the config

```powershell
$DISCLOSURE_PATCH = @'
{
  "name": "India Sales Bot",
  "is_active": true,
  "ai_disclosure_enabled": true,
  "ai_disclosure_text": "Important: this call is handled by an AI assistant and may be recorded.",
  "graph_json": {
    "nodes": [
      {"id":"stt_1","type":"STT","config":{"provider":"deepgram","language":"en-IN"}},
      {"id":"llm_1","type":"LLM","config":{"provider":"gemini","system_prompt":"You are a helpful sales assistant.","max_tokens":200}},
      {"id":"tts_1","type":"TTS","config":{"provider":"cartesia"}}
    ],
    "edges":[{"from":"stt_1","to":"llm_1"},{"from":"llm_1","to":"tts_1"}]
  }
}
'@

Invoke-RestMethod -Method Put -Uri "http://localhost:8000/api/v1/configs/$CONFIG_ID/" `
  -Headers @{Authorization="Bearer $TOKEN_IN"; "Content-Type"="application/json"} `
  -Body $DISCLOSURE_PATCH | ConvertTo-Json
```

### 7.2 Verify disclosure in Python shell

```powershell
python manage.py shell -c "
from apps.ai_engine.models import AIConfig
cfg = AIConfig.objects.get(pk=$CONFIG_ID)
print('Disclosure enabled:', cfg.ai_disclosure_enabled)
print('Disclosure text:   ', cfg.ai_disclosure_text)

# Simulate what GraphContext does
from apps.ai_engine.executor import GraphContext
ctx = GraphContext('test-call-001', compliance_prefix=cfg.ai_disclosure_text if cfg.ai_disclosure_enabled else '')
print('First call prefix: ', repr(ctx.get_disclosure_prefix()))
print('Second call prefix:', repr(ctx.get_disclosure_prefix()))  # must be empty
"
```

**Expected output:**
```
Disclosure enabled: True
Disclosure text:    Important: this call is handled by an AI assistant and may be recorded.
First call prefix:  'Important: this call is handled by an AI assistant and may be recorded. '
Second call prefix: ''
```

✅ **Pass criteria:** Prefix returned exactly once; empty on all subsequent calls.

---

## 8. Test: Shadow Ledger (Task 3)

### 8.1 Seed provider cost rates

```powershell
python manage.py shell -c "
from apps.billing.models import ProviderCostRate

rates = [
    {'provider':'deepgram', 'service_type':'stt',  'cost_per_unit':'0.000059', 'unit':'per_second'},
    {'provider':'cartesia', 'service_type':'tts',  'cost_per_unit':'0.000065', 'unit':'per_second'},
    {'provider':'gemini',   'service_type':'llm',  'cost_per_unit':'0.000003', 'unit':'per_1k_tokens'},
    {'provider':'openai',   'service_type':'llm',  'cost_per_unit':'0.000015', 'unit':'per_1k_tokens'},
    {'provider':'openai',   'service_type':'tts',  'cost_per_unit':'0.000015', 'unit':'per_character'},
]
for r in rates:
    ProviderCostRate.objects.get_or_create(
        provider=r['provider'], service_type=r['service_type'],
        defaults=r
    )
print('Rates seeded:', ProviderCostRate.objects.count())
"
```

### 8.2 Simulate a call and run billing

```powershell
python manage.py shell -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

from apps.calls.models import Call
from apps.ai_engine.models import AIConfig
from apps.tenants.models import Tenant
from apps.billing.models import BillingAccount, Ledger

t = Tenant.objects.get(name='Acme India')
cfg = AIConfig.objects.filter(tenant=t, is_active=True).first()

# Create a fake in-progress call
call = Call.objects.create(
    tenant=t, ai_config=cfg,
    livekit_room_id='test-room-shadow-001',
    status='IN_PROGRESS',
)
print(f'Created call id={call.id}')

# Run billing cycle directly (synchronous)
from apps.billing.tasks import calculate_realtime_billing
calculate_realtime_billing()

# Read ledger
entries = Ledger.objects.filter(call=call)
for e in entries:
    print(f'  retail={e.retail_charge_cents}c  provider_cost={e.provider_cost_cents}c  margin={e.margin_cents}c')
    print(f'  breakdown: {e.provider_cost_breakdown}')
"
```

**Expected output:**
```
Created call id=3
  retail=50c  provider_cost=12c  margin=38c
  breakdown: {'deepgram': 5, 'cartesia': 4, 'gemini': 3}
```

✅ **Pass criteria:** `retail_charge_cents > 0`, `provider_cost_cents > 0`, `margin_cents = retail - cost`.

### 8.3 Verify balance was deducted

```powershell
python manage.py shell -c "
from apps.billing.models import BillingAccount
from apps.tenants.models import Tenant
t = Tenant.objects.get(name='Acme India')
acct = BillingAccount.objects.get(tenant=t)
print(f'Balance: {acct.balance_cents}c  (started at 100000c)')
"
```

---

## 9. Test: API Tooling System (Task 5)

### 9.1 Spin up a mock API endpoint

```powershell
# In a new terminal — tiny mock server
python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'order_status':'shipped','eta':'2 days'}).encode())
    def log_message(self, *a): pass

print('Mock API on :9999')
HTTPServer(('', 9999), H).serve_forever()
"
```

### 9.2 Register the tool in the DB

```powershell
python manage.py shell -c "
from apps.ai_engine.models import AIConfig, AgentTool
from apps.tenants.models import Tenant

t   = Tenant.objects.get(name='Acme India')
cfg = AIConfig.objects.filter(tenant=t, is_active=True).first()

tool = AgentTool.objects.create(
    ai_config=cfg,
    name='check_order_status',
    description='Check the delivery status of an order by order_id.',
    method='GET',
    url_template='http://localhost:9999/orders/{order_id}',
    headers={},
    body_template={},
    timeout_sec=5,
)
print(f'AgentTool created: id={tool.id} name={tool.name}')
"
```

### 9.3 Test APIToolNode directly

```powershell
python manage.py shell -c "
import asyncio, django
from apps.ai_engine.executor import APIToolNode, GraphContext

async def test():
    ctx = GraphContext('tool-test-001')
    ctx.variables['order_id'] = '12345'

    node = APIToolNode('tool_node_1', {
        'tool_name': 'check_order_status',
        'ai_config_id': 1,          # adjust to your AIConfig id
    })

    print('Calling tool...')
    await node.process(ctx)

    result = ctx.variables.get('tool_result_check_order_status', 'NOT SET')
    print('Tool result:', result)
    assert 'shipped' in result, 'Expected shipped status in result'
    print('PASS')

asyncio.run(test())
"
```

**Expected output:**
```
Calling tool...
Tool result: {"order_status": "shipped", "eta": "2 days"}
PASS
```

✅ **Pass criteria:** Tool result stored in `context.variables`, contains API response.

---

## 10. Test: PII Masking

```powershell
python manage.py shell -c "
from apps.calls.pii import mask_pii

cases = [
    ('My number is 9876543210 and email is foo@bar.com', 'phone+email'),
    ('Aadhaar: 1234 5678 9012', 'aadhaar'),
    ('PAN: ABCDE1234F', 'pan'),
    ('NI: AB 12 34 56 C', 'uk NI'),
    ('Card: 4111 1111 1111 1111', 'card'),
    ('DOB: 12/05/1990', 'dob'),
    ('Server IP is 192.168.1.1', 'ip'),
]

all_pass = True
for text, label in cases:
    masked = mask_pii(text)
    original_leaked = any(t in masked for t in ['9876543210','foo@bar.com','1234 5678','ABCDE1234F','AB 12 34','4111','12/05/1990','192.168.1.1'])
    status = 'FAIL' if original_leaked else 'PASS'
    if original_leaked: all_pass = False
    print(f'  [{status}] {label}: {masked}')

print()
print('All PII masked:', all_pass)
"
```

**Expected:**
```
  [PASS] phone+email: My number is [PHONE] and email is [EMAIL]
  [PASS] aadhaar: Aadhaar: [AADHAAR]
  [PASS] pan: PAN: [PAN]
  [PASS] uk NI: NI: [NI]
  [PASS] card: Card: [CARD]
  [PASS] dob: DOB: [DOB]
  [PASS] ip: Server IP is [IP]

All PII masked: True
```

---

## 11. Test: Voice Pipeline (end-to-end audio)

This tests the actual Deepgram → Gemini → Cartesia pipeline.
Requires all API keys in `.env`.

### 11.1 Mic test (speak and hear response)

```powershell
python test_pipeline.py --mode mic
```

Speak anything. You should see:
```
[USER]  your transcribed words
[AI]    streamed response chunks
[SYSTEM] LLM TTFT: Xms  E2E: Xms ✓
```

Press `Ctrl+C` to stop.

### 11.2 WAV file test (no microphone needed)

```powershell
# Record a short WAV first (requires sox or ffmpeg)
# OR use any existing 16kHz mono WAV file

python test_pipeline.py --mode file --input your_audio.wav --output reply.wav
```

✅ **Pass criteria:** `reply.wav` created, E2E latency printed, no exceptions.

---

## 12. Run automated Django tests

```powershell
# All apps
python -m pytest

# Individual app
python -m pytest apps/ai_engine/tests.py -v
python -m pytest apps/billing/tests.py -v
python -m pytest apps/calls/tests.py -v
```

---

## 13. Quick sanity checklist (run everything at once)

```powershell
python manage.py shell -c "
print('--- Sanity Checks ---')

# DB
from apps.tenants.models import Tenant
from apps.users.models import User
from apps.ai_engine.models import AIConfig, AgentTool
from apps.billing.models import BillingAccount, Ledger, ProviderCostRate
from apps.calls.models import Call, Transcript

print(f'Tenants:          {Tenant.objects.count()}')
print(f'Users:            {User.objects.count()}')
print(f'AIConfigs:        {AIConfig.objects.count()}')
print(f'AgentTools:       {AgentTool.objects.count()}')
print(f'ProviderRates:    {ProviderCostRate.objects.count()}')
print(f'BillingAccounts:  {BillingAccount.objects.count()}')
print(f'Ledger entries:   {Ledger.objects.count()}')
print(f'Calls:            {Call.objects.count()}')

# RBAC
roles = list(User.objects.values_list('role', flat=True))
print(f'Roles present:    {sorted(set(roles))}')

# Data residency
t = Tenant.objects.filter(region='IN').first()
if t: print(f'India cloud_region: {t.cloud_region}')
t = Tenant.objects.filter(region='UK').first()
if t: print(f'UK cloud_region:    {t.cloud_region}')

# PII
from apps.calls.pii import mask_pii
assert '[PHONE]' in mask_pii('Call me on 9876543210')
print('PII masking:      OK')

# Compliance
from apps.ai_engine.executor import GraphContext
ctx = GraphContext('x', compliance_prefix='AI DISCLOSURE')
assert ctx.get_disclosure_prefix() == 'AI DISCLOSURE '
assert ctx.get_disclosure_prefix() == ''
print('Compliance prefix: OK')

print()
print('All checks passed.')
"
```

---

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `redis.exceptions.ConnectionError` | Redis not running | `docker start redis` or `redis-server` |
| `ModuleNotFoundError: livekit` | LiveKit SDK not installed | `pip install livekit livekit-agents` |
| `OperationalError: no such table` | Migration not run | `python manage.py migrate` |
| `Invalid token` on API call | Token expired (1h lifetime) | Re-run the login step |
| `LLM warmup failed` | API key missing or wrong | Check `.env` GEMINI_API_KEY |
| `E2E > 840ms ✗` | Cold LLM start | Run mic test twice — warmup fires on first `start()` |
