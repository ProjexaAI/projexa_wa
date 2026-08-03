import json
import time
from openai import OpenAI
from config import OPENCODE_API_KEY, OPENCODE_MODEL, OPENCODE_BASE_URL
from agent.prompts import build_system_prompt, load_filtered_docs, SCHEMA_COLLECTIONS, HUMANIZER_SYSTEM_PROMPT
from agent.functions import FUNCTIONS, execute_function, get_user_context
from agent.intent import (
    detect_intents, get_relevant_schemas, get_relevant_function_docs,
    get_relevant_tools, is_full_context_needed, INTENTS as INTENT_DEFS
)
from agent.query_validator import validate_query, TIMEOUT_SECONDS
from agent.db import get_collection
from agent.permissions import get_allowed_collections
from bson import ObjectId

client = OpenAI(api_key=OPENCODE_API_KEY, base_url=OPENCODE_BASE_URL)

import logging
logger = logging.getLogger("webhook")


def humanize_response(raw_text: str, user_name: str) -> str:
    """Pass raw AI response through a second LLM to make it sound natural on WhatsApp."""
    if not raw_text or not raw_text.strip():
        return raw_text
    try:
        response = client.chat.completions.create(
            model=OPENCODE_MODEL,
            messages=[
                {"role": "system", "content": HUMANIZER_SYSTEM_PROMPT},
                {"role": "user", "content": f"USER: {user_name}\n\nRAW RESPONSE:\n{raw_text}"}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        humanized = response.choices[0].message.content
        if humanized and humanized.strip():
            logger.info(f"[HUMANIZER] Raw {len(raw_text)} chars -> Humanized {len(humanized)} chars")
            return humanized.strip()
        return raw_text
    except Exception as e:
        logger.warning(f"[HUMANIZER] Failed, using raw response: {e}")
        return raw_text

# Conversation history: {user_id: {"messages": [...], "timestamp": float}}
CONVERSATION_HISTORY: dict[str, dict] = {}
HISTORY_TTL_SECONDS = 900  # 15 minutes
MAX_HISTORY_MESSAGES = 20  # Keep last 20 messages (user + assistant pairs)

# Simple cache for user/team data: {cache_key: {"data": ..., "timestamp": float}}
_DATA_CACHE: dict[str, dict] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached(key: str):
    """Get cached data if still valid."""
    entry = _DATA_CACHE.get(key)
    if entry and time.time() - entry["timestamp"] < CACHE_TTL_SECONDS:
        return entry["data"]
    return None


def _set_cached(key: str, data):
    """Cache data with timestamp."""
    _DATA_CACHE[key] = {"data": data, "timestamp": time.time()}
    # Prune old entries if cache grows too large
    if len(_DATA_CACHE) > 100:
        oldest_keys = sorted(_DATA_CACHE.keys(), key=lambda k: _DATA_CACHE[k]["timestamp"])[:50]
        for k in oldest_keys:
            del _DATA_CACHE[k]

# Convert function registry to OpenAI function calling format
TOOL_DEFINITIONS = []
for name, func in FUNCTIONS.items():
    properties = {}
    required = []
    for param_name, param_type in func["params"].items():
        if "optional" in param_type.lower():
            properties[param_name] = {"type": "string", "description": param_type}
        else:
            properties[param_name] = {"type": "string", "description": param_type}
            required.append(param_name)

    TOOL_DEFINITIONS.append({
        "type": "function",
        "function": {
            "name": name,
            "description": func["description"],
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    })

# Add custom MongoDB query tool
TOOL_DEFINITIONS.append({
    "type": "function",
    "function": {
        "name": "execute_mongodb_query",
        "description": "Execute a read-only MongoDB query when no predefined function exists. Only for READ operations.",
        "parameters": {
            "type": "object",
            "properties": {
                "collection": {"type": "string", "description": "Collection name to query"},
                "filter": {"type": "object", "description": "MongoDB filter/query"},
                "projection": {"type": "object", "description": "Fields to include/exclude"},
                "sort": {"type": "object", "description": "Sort order"},
                "limit": {"type": "number", "description": "Max results (default 20, max 100)"}
            },
            "required": ["collection", "filter"]
        }
    }
})

# Send media tool — allows LLM to send images, videos, documents to the user
TOOL_DEFINITIONS.append({
    "type": "function",
    "function": {
        "name": "send_media",
        "description": "Send an image, video, or document to the user via WhatsApp. Use this when the user asks to see a photo, file, document, or any media. The URL must be a direct link to the file (e.g., from CDN or public URL).",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Direct URL to the media file"},
                "type": {"type": "string", "description": "Media type: image, video, or document"},
                "caption": {"type": "string", "description": "Optional caption to send with the media"}
            },
            "required": ["url", "type"]
        }
    }
})


def _serialize(doc):
    """Serialize MongoDB document to JSON-safe dict. Handles ObjectId, datetime, and nested objects."""
    try:
        if doc is None:
            return None
        if isinstance(doc, list):
            return [_serialize(d) for d in doc]
        if isinstance(doc, dict):
            result = {}
            for k, v in doc.items():
                try:
                    if isinstance(v, ObjectId):
                        result[k] = str(v)
                    elif hasattr(v, 'isoformat'):
                        result[k] = v.isoformat()
                    elif isinstance(v, dict):
                        result[k] = _serialize(v)
                    elif isinstance(v, list):
                        result[k] = [_serialize(i) for i in v]
                    elif isinstance(v, (int, float, str, bool)):
                        result[k] = v
                    else:
                        result[k] = str(v)
                except Exception:
                    result[k] = str(v) if v is not None else None
            return result
        return doc
    except Exception:
        return {"_serialization_error": True}


def _cast_object_ids(filter_query: dict) -> dict:
    """
    Cast string values to ObjectId for fields that typically store ObjectIds.
    This handles the case where the AI generates queries with string IDs.
    """
    # Fields that typically store ObjectId values
    ID_FIELDS = {
        "_id", "userId", "studentId", "mentorId", "enrollmentId",
        "assignmentId", "leaderId", "memberId", "teamId", "trackId",
        "sessionId", "trackSessionConfigId", "announcementId",
        "interactionId", "notificationId", "inviterId", "inviteeId"
    }

    result = {}
    for k, v in filter_query.items():
        if k.startswith("$"):
            # Handle logical operators ($or, $and, etc.)
            if isinstance(v, list):
                result[k] = [_cast_object_ids(item) if isinstance(item, dict) else item for item in v]
            elif isinstance(v, dict):
                result[k] = _cast_object_ids(v)
            else:
                result[k] = v
        elif k in ID_FIELDS and isinstance(v, str) and len(v) == 24:
            try:
                result[k] = ObjectId(v)
            except Exception:
                result[k] = v
        elif isinstance(v, dict):
            result[k] = _cast_object_ids(v)
        elif isinstance(v, list):
            result[k] = [
                _cast_object_ids(item) if isinstance(item, dict)
                else (ObjectId(item) if isinstance(item, str) and len(item) == 24 else item)
                for item in v
            ]
        else:
            result[k] = v
    return result


def execute_custom_query(params: dict, user_role: str, allowed_read: list) -> dict:
    collection = params.get("collection", "")

    # Permission check
    if allowed_read != "*" and collection not in allowed_read:
        return {"error": f"Permission denied: cannot read from {collection}"}

    # Validate query is read-only
    is_valid, msg = validate_query(params)
    if not is_valid:
        return {"error": f"Query validation failed: {msg}"}

    try:
        col = get_collection(collection)
        filter_query = _cast_object_ids(params.get("filter", {}))
        projection = params.get("projection")
        sort = params.get("sort")
        limit = min(params.get("limit", 20), 100)

        cursor = col.find(filter_query, projection)

        if sort:
            sort_list = [(k, v) for k, v in sort.items()]
            cursor = cursor.sort(sort_list)

        results = list(cursor.limit(limit))

        return {"results": _serialize(results), "count": len(results)}
    except Exception as e:
        return {"error": str(e)}


def _get_message_role(msg) -> str:
    """Extract role from either dict or ChatCompletionMessage object."""
    if isinstance(msg, dict):
        return msg.get("role", "")
    return getattr(msg, "role", "")


def _message_to_dict(msg) -> dict:
    """Convert message to dict. Handles both dict and ChatCompletionMessage."""
    if isinstance(msg, dict):
        return msg
    # ChatCompletionMessage — convert to dict
    result = {"role": getattr(msg, "role", "")}
    content = getattr(msg, "content", None)
    if content:
        result["content"] = content
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            }
            for tc in tool_calls
        ]
    tool_call_id = getattr(msg, "tool_call_id", None)
    if tool_call_id:
        result["tool_call_id"] = tool_call_id
    return result


def _load_history(user_id: str) -> list[dict]:
    entry = CONVERSATION_HISTORY.get(user_id)
    if not entry:
        return []
    if time.time() - entry["timestamp"] > HISTORY_TTL_SECONDS:
        del CONVERSATION_HISTORY[user_id]
        return []
    # Filter out system messages to avoid duplication
    return [m for m in entry["messages"] if _get_message_role(m) != "system"]


def _save_history(user_id: str, messages: list):
    # Convert all messages to dicts and filter out system messages
    filtered = []
    for m in messages:
        role = _get_message_role(m)
        if role != "system":
            filtered.append(_message_to_dict(m))
    trimmed = filtered[-MAX_HISTORY_MESSAGES:]
    CONVERSATION_HISTORY[user_id] = {
        "messages": trimmed,
        "timestamp": time.time()
    }


def _build_filtered_tool_defs(relevant_tool_names: list[str]) -> list[dict]:
    """Build OpenAI tool definitions for only the relevant tools."""
    tools = []
    for name in relevant_tool_names:
        if name in TOOL_DEFINITIONS_MAP:
            tools.append(TOOL_DEFINITIONS_MAP[name])
    return tools


# Pre-build a lookup map for tool definitions
TOOL_DEFINITIONS_MAP = {}
for _td in TOOL_DEFINITIONS:
    TOOL_DEFINITIONS_MAP[_td["function"]["name"]] = _td


def _build_filtered_system_prompt(user_id: str, user_name: str, user_role: str,
                                  allowed_read: list, allowed_write: list,
                                  user_context: str, intents: set[str]) -> str:
    """Build system prompt with only intent-relevant docs."""
    relevant_schemas = get_relevant_schemas(intents)
    relevant_func_docs = get_relevant_function_docs(intents)

    docs = load_filtered_docs(
        user_role=user_role,
        allowed_read=allowed_read,
        intents=intents,
        relevant_schemas=relevant_schemas,
        relevant_function_docs=relevant_func_docs,
    )

    read_list = "ALL" if allowed_read == "*" else ", ".join(allowed_read)
    write_list = "ALL" if allowed_write == "*" else ", ".join(allowed_write)

    context_block = f"\n{user_context}\n" if user_context else ""

    prompt = f"""You are an AI assistant for Projexa Internship Management System. You help students, mentors, and admins manage their internship data via WhatsApp.

## User Context
- User ID: {user_id}
- Name: {user_name}
- Role: {user_role}
- Allowed Read Collections: {read_list}
- Allowed Write Collections: {write_list}
{context_block}

## Documentation

{docs}

## Rules

1. **For WRITE operations**: ALWAYS use the predefined functions. Never generate write queries.
2. **For READ operations**: Use predefined functions if available. If no predefined function exists, you may generate a MongoDB read query.
3. **NEVER** access collections not in the user's allowed read/write list.
4. **NEVER** use write operators ($set, $push, $insert, etc.) in custom queries.
5. Keep responses concise and formatted for WhatsApp (no markdown tables, use simple text).
6. If the user asks something unrelated to the system, politely redirect them.
7. When showing data, format it nicely for WhatsApp (bullet points, line breaks).
8. If a function returns an error, explain it to the user in simple terms.
9. **When a student asks "who is my mentor?"**, use `get_student_mentor` with their user ID. Do NOT run custom queries against enrollment or assignment collections.
10. **Avoid large result sets**: When listing teams, always filter by `track_config_id` if the user mentions a specific track. Never dump all teams for a session into context.
11. **Minimize context bloat**: If a function returns many results, summarize them instead of including the full data in subsequent AI calls.
12. **When results are empty**: If a function returns 0 results, explain WHY to the user. For example: "There are announcements in the system, but none are currently targeted to your track or role." Never just say "no data found" without context.
13. **Media support**: When a function returns documents with `files` array OR `attachments` array, each item has a `url` or `fileUrl` field. Use that exact URL value when calling `send_media`. Do NOT construct, modify, or guess URLs — use the URL field as-is. Call `send_media` with `type: "document"` for PDFs/files/spreadsheets. If an announcement has attachments, send them as documents — do NOT just describe them in text.
14. **Use the User Context above**: The "User Context" section contains the user's current session ID, track config ID, enrollment ID, team info, and mentor info. Use these values directly when calling functions — do NOT ask the user for IDs you already have. For example, to find a student's team, call `list_teams(member_id=user_id)`.
15. **NEVER hallucinate data**: ONLY use data returned by function calls. If a function returns document titles, use THOSE exact titles. If a function returns scores, use THOSE exact numbers. NEVER make up document names, scores, dates, or any other data. If the function result doesn't contain what the user is asking for, say "I don't have that information" rather than guessing.
16. **Anticipate intent, not literal words** — When a user asks about something, consider what they're really trying to understand. If they ask "does it have marks?" about documents, they likely mean "is there a marks criteria attached?" not "have marks been scored yet?" Think about what question comes *next* and answer proactively.
17. **Lead with the answer** — Start your response with the direct answer (yes/no/value/explanation), then elaborate only if needed. Don't bury the answer in paragraphs of context. Default to 1-3 sentences unless the user asks for detail.
18. **Only discuss what's in their track** — The "User Context" section lists the student's track criteria (attendance, marks, documents, interactions, etc.). If a topic is NOT listed in their context (e.g., no attendance section means their track has no attendance component, no interactions section means no interaction sessions), do NOT discuss it. Don't say "0 attendance records" or "0 interactions" — instead say "Your track doesn't have attendance/interaction tracking." This matches the web app sidebar which hides irrelevant tabs.
19. **Use the Available Capabilities list** — When asked "what can you do?", ONLY list items from the "Available Capabilities" section in the User Context. Do NOT add capabilities from the function docs that aren't in that list. If a capability isn't listed, it's not available for this user's track.
20. **ZERO GREETINGS** — Your response must NEVER start with "Hi", "Hey", "Hello", or the user's name. NEVER. Not even once. Not even on the first message. Just answer the question. If they say "hi", just say "What can I help you with?" — no name, no emoji, no greeting. If they ask about documents, start with "I checked your documents" — not "Hey Harshit, I checked your documents". The words "Hey", "Hi", "Hello" should NEVER appear in your response. EVER.
21. **NO NAME IN RESPONSES** — NEVER use the user's name in your response. Not "Hey Harshit", not "Harshit, I found...", not "Your documents, Harshit". Just say "I found..." or "Your documents...". The user's name is in the system context for YOUR reference only — never output it.
22. **One message = one answer** — Treat each message as a continuation of the conversation. The user has history. Do NOT re-introduce yourself. Do NOT re-explain what you can do. Just answer what they asked.
"""
    return prompt


def process_message(user_id: str, user_name: str, user_role: str, message: str) -> dict:
    """
    Process a user message and return a response with optional media.

    Returns:
        dict with keys:
            - text (str): The text response
            - media (list): Optional list of media items, each with:
                - url (str): URL or file path to the media
                - type (str): "image", "video", "document", or "audio"
                - caption (str): Optional caption
    """
    allowed = get_allowed_collections(user_role)
    allowed_read = allowed["read"]
    allowed_write = allowed["write"]

    # Step 1: Detect intent from user message
    intents = detect_intents(message, user_role, client, OPENCODE_MODEL)
    use_filtered = not is_full_context_needed(intents)

    # Step 2: Fetch user context
    user_ctx = get_user_context(user_id, user_role)

    # Step 3: Build system prompt (filtered or full)
    if use_filtered:
        system_prompt = _build_filtered_system_prompt(
            user_id=user_id,
            user_name=user_name,
            user_role=user_role,
            allowed_read=allowed_read,
            allowed_write=allowed_write,
            user_context=user_ctx,
            intents=intents,
        )
        relevant_tools = get_relevant_tools(intents)
        active_tool_defs = _build_filtered_tool_defs(relevant_tools)
        logger.info(f"[INTENT] Filtered mode: {len(intents)} intents, {len(relevant_tools)} tools, {len(active_tool_defs)} tool_defs")
    else:
        system_prompt = build_system_prompt(
            user_id=user_id,
            user_name=user_name,
            user_role=user_role,
            allowed_read=allowed_read,
            allowed_write=allowed_write,
            user_context=user_ctx,
        )
        active_tool_defs = TOOL_DEFINITIONS
        logger.info(f"[INTENT] Full mode: {len(TOOL_DEFINITIONS)} tools")

    # Step 4: Load conversation history
    history = _load_history(user_id)

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    # Track media items from send_media tool calls
    pending_media = []
    collected_intents = set(intents)  # Track all intents encountered during tool calls

    # Function calling loop (max 10 iterations)
    for iteration in range(10):
        response = client.chat.completions.create(
            model=OPENCODE_MODEL,
            messages=messages,
            tools=active_tool_defs,
            tool_choice="auto",
            reasoning_effort="high"
        )

        choice = response.choices[0]

        # If no tool call, return the text response
        if not choice.message.tool_calls:
            final_text = choice.message.content or "I couldn't process your request."
            _save_history(user_id, messages + [
                {"role": "assistant", "content": final_text}
            ])
            if pending_media:
                return {"text": "", "media": pending_media}
            final_text = humanize_response(final_text, user_name)
            return {"text": final_text, "media": pending_media}

        # Process tool calls
        messages.append(choice.message)

        for tool_call in choice.message.tool_calls:
            func_name = tool_call.function.name
            try:
                func_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            # Handle send_media — capture and return to caller
            if func_name == "send_media":
                media_item = {
                    "url": func_args.get("url", ""),
                    "type": func_args.get("type", "document"),
                    "caption": func_args.get("caption", "")
                }
                pending_media.append(media_item)
                result = {"status": "queued", "type": media_item["type"]}
            # Handle custom MongoDB query
            elif func_name == "execute_mongodb_query":
                result = execute_custom_query(func_args, user_role, allowed_read)
                # Detect intent from queried collection
                queried_col = func_args.get("collection", "")
                for intent_name, intent_cfg in INTENT_DEFS.items():
                    for schema_file in intent_cfg["schemas"]:
                        cols = SCHEMA_COLLECTIONS.get(schema_file, [])
                        if queried_col in cols:
                            collected_intents.add(intent_name)
            else:
                # Handle predefined function
                func_def = FUNCTIONS.get(func_name, {})
                converted_args = {}
                for k, v in func_args.items():
                    if isinstance(v, str):
                        if k.endswith("_id") and len(v) == 24:
                            converted_args[k] = v
                        elif v.isdigit():
                            converted_args[k] = int(v)
                        elif v.replace(".", "").isdigit():
                            converted_args[k] = float(v)
                        else:
                            converted_args[k] = v
                    else:
                        converted_args[k] = v

                result = execute_function(func_name, converted_args, user_role)

                # Track intent from function's collection
                if func_def:
                    func_collection = func_def.get("collection", "")
                    for intent_name, intent_cfg in INTENT_DEFS.items():
                        for schema_file in intent_cfg["schemas"]:
                            cols = SCHEMA_COLLECTIONS.get(schema_file, [])
                            if func_collection in cols:
                                collected_intents.add(intent_name)

            # Log function result for debugging
            result_str = json.dumps(result, default=str)
            logger.info(f"[FUNC_RESULT] {func_name} | args={func_args} | result={result_str}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_str
            })

        # Dynamic tool expansion: if new intents emerged from tool results,
        # add their tools to the active set for the next iteration
        if use_filtered and collected_intents - intents:
            new_intents = collected_intents - intents
            intents = collected_intents
            new_tools = get_relevant_tools(new_intents)
            # Add new tools that aren't already in active_tool_defs
            existing_names = {t["function"]["name"] for t in active_tool_defs}
            for tool_name in new_tools:
                if tool_name not in existing_names and tool_name in TOOL_DEFINITIONS_MAP:
                    active_tool_defs.append(TOOL_DEFINITIONS_MAP[tool_name])
                    logger.info(f"[INTENT] Expanded tools: added {tool_name}")

    # If we've exceeded iterations, save what we have and return
    final_text = "I processed your request but needed more steps. Please try a simpler query."
    _save_history(user_id, messages + [{"role": "assistant", "content": final_text}])
    final_text = humanize_response(final_text, user_name)
    return {"text": final_text, "media": pending_media}
