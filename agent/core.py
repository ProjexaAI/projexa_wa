import json
import time
from openai import OpenAI
from config import OPENCODE_API_KEY, OPENCODE_MODEL, OPENCODE_BASE_URL
from agent.prompts import build_system_prompt
from agent.functions import FUNCTIONS, execute_function
from agent.query_validator import validate_query, TIMEOUT_SECONDS
from agent.summarizer import summarize_result
from agent.db import get_collection
from agent.permissions import get_allowed_collections
from bson import ObjectId

client = OpenAI(api_key=OPENCODE_API_KEY, base_url=OPENCODE_BASE_URL)

# Conversation history: {user_id: {"messages": [...], "timestamp": float}}
CONVERSATION_HISTORY: dict[str, dict] = {}
HISTORY_TTL_SECONDS = 900  # 15 minutes
MAX_HISTORY_MESSAGES = 20  # Keep last 20 messages (user + assistant pairs)

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
        filter_query = params.get("filter", {})
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


def _load_history(user_id: str) -> list[dict]:
    entry = CONVERSATION_HISTORY.get(user_id)
    if not entry:
        return []
    if time.time() - entry["timestamp"] > HISTORY_TTL_SECONDS:
        del CONVERSATION_HISTORY[user_id]
        return []
    return entry["messages"]


def _save_history(user_id: str, messages: list[dict]):
    trimmed = messages[-MAX_HISTORY_MESSAGES:]
    CONVERSATION_HISTORY[user_id] = {
        "messages": trimmed,
        "timestamp": time.time()
    }


def _build_conversation_context(messages: list) -> str:
    """
    Build a short context string from recent messages for the summarizer.
    Extracts the last 2-3 user/assistant message pairs to understand intent.
    """
    context_parts = []
    # Look at last 6 messages (3 pairs of user/assistant)
    recent = messages[-6:] if len(messages) > 6 else messages

    for msg in recent:
        # Handle both dict and ChatCompletionMessage objects
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "")
            content = getattr(msg, "content", "") or ""

        if not content:
            continue
        # Skip system messages and tool messages
        if role in ("system", "tool"):
            continue
        # Truncate long messages
        if len(content) > 200:
            content = content[:200] + "..."
        if role == "user":
            context_parts.append(f"User: {content}")
        elif role == "assistant":
            context_parts.append(f"Assistant: {content}")

    return "\n".join(context_parts[-4:])  # Last 4 lines max


def process_message(user_id: str, user_name: str, user_role: str, message: str) -> str:
    allowed = get_allowed_collections(user_role)
    allowed_read = allowed["read"]
    allowed_write = allowed["write"]

    system_prompt = build_system_prompt(
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        allowed_read=allowed_read,
        allowed_write=allowed_write
    )

    # Load prior conversation history
    history = _load_history(user_id)

    # Build messages: system prompt + history + new user message
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    # Function calling loop (max 10 iterations to prevent infinite loops)
    for _ in range(10):
        response = client.chat.completions.create(
            model=OPENCODE_MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto"
        )

        choice = response.choices[0]

        # If no tool call, return the text response
        if not choice.message.tool_calls:
            final_text = choice.message.content or "I couldn't process your request."
            # Save conversation: user message + assistant response
            _save_history(user_id, messages + [
                {"role": "assistant", "content": final_text}
            ])
            return final_text

        # Process tool calls
        messages.append(choice.message)

        for tool_call in choice.message.tool_calls:
            func_name = tool_call.function.name
            try:
                func_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            # Handle custom MongoDB query
            if func_name == "execute_mongodb_query":
                result = execute_custom_query(func_args, user_role, allowed_read)
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

            # Summarize large results before injecting into context
            conv_context = _build_conversation_context(messages)
            summarized = summarize_result(
                raw_result=result,
                function_name=func_name,
                function_params=func_args,
                user_message=message,
                conversation_context=conv_context
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": summarized
            })

    # If we've exceeded iterations, save what we have and return
    final_text = "I processed your request but needed more steps. Please try a simpler query."
    _save_history(user_id, messages + [{"role": "assistant", "content": final_text}])
    return final_text
