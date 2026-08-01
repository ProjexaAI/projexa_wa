# AGENTS.md

## Project

WhatsApp AI chatbot for Projexa Internship Management System. Python FastAPI app that receives WhatsApp webhooks, processes messages via OpenAI-compatible API (MiMo V2.5 Free), and performs MongoDB operations through predefined functions.

## Architecture

```
server.py                    # FastAPI webhook entry point
agent/
  core.py                    # AI processing loop with function calling
  functions.py               # 40+ predefined DB functions (registry at bottom)
  db.py                      # MongoDB connection (pymongo)
  permissions.py             # Role-based access (ADMIN/MENTOR/STUDENT)
  prompts.py                 # System prompt builder, loads docs/ into context (filtered by role)
  query_validator.py         # Enforces read-only on custom MongoDB queries
```

## Run

```bash
# Development
pip install -r requirements.txt
python server.py             # Starts on 0.0.0.0:8000

# Docker
docker-compose up --build
```

## Environment

Copy `.env.example` to `.env`. Required vars:
- `MONGODB_URI`, `MONGODB_DB_NAME` — MongoDB connection
- `OPENCODE_API_KEY` — OpenAI-compatible API key
- `OPENWA_API_URL`, `OPENWA_API_KEY`, `OPENWA_SESSION_ID` — WhatsApp gateway

## Critical Rules

1. **Writes only via predefined functions** — Never generate write queries. The `query_validator.py` blocks all write operators (`$set`, `$push`, etc.) in custom queries.

2. **Role permissions are enforced at two layers** — `permissions.py` checks collection access; `FUNCTIONS` registry in `functions.py:1505` maps each function to its required permission. When adding a new function, register it in `FUNCTIONS` dict.

3. **User lookup by phone** — `permissions.py:get_user_by_phone()` uses multi-strategy matching (exact, digits-only, last-10 regex). WhatsApp sends `@lid` or `@c.us` suffixed phone numbers; both are handled.

4. **Context bloat is a real problem** — `prompts.py:load_docs()` filters schema and function docs by role. Function results go directly to the AI without summarization. If functions return large payloads, improve the function to return only needed fields.

5. **Conversation history** — 15-minute TTL, max 20 messages per user, stored in-memory (lost on restart). System messages are stripped from history to avoid duplication.

6. **Docs are loaded into every AI prompt** — `prompts.py:load_docs()` reads all `docs/schema/*.md` and `docs/functions/*.md` files at runtime. Keep these docs accurate; they directly control AI behavior.

7. **ObjectId casting** — `core.py:_cast_object_ids()` automatically converts 24-char strings to ObjectId for known ID fields. If adding new collections with ObjectId references, update the `ID_FIELDS` set in `core.py:143`.

8. **Function registry is the source of truth** — `FUNCTIONS` dict in `functions.py:1505` defines all available tools. The `description` field becomes the OpenAI tool description the model sees. Write clear descriptions.

## Adding a New Function

1. Write handler function in `functions.py`
2. Add to `FUNCTIONS` dict with `description`, `params`, `handler`, `permission`, `collection`
3. If large results, improve the function to return only needed fields
4. If new collection, update `ROLE_PERMISSIONS` in `permissions.py`
5. If new ObjectId field, add to `ID_FIELDS` in `core.py`

## Testing

No test suite exists. Test manually by sending WhatsApp messages or calling the webhook:
```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"event":"message.received","data":{"from":"<phone>@c.us","body":"hello","type":"text"}}'
```

Health check: `GET /health`
