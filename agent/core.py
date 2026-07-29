import json
from openai import OpenAI
from config import OPENCODE_API_KEY, OPENCODE_MODEL, OPENCODE_BASE_URL
from agent.prompts import build_system_prompt
from agent.functions import FUNCTIONS, execute_function
from agent.query_validator import validate_query, TIMEOUT_SECONDS
from agent.db import get_collection
from agent.permissions import get_allowed_collections
from bson import ObjectId

client = OpenAI(api_key=OPENCODE_API_KEY, base_url=OPENCODE_BASE_URL)

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
    if doc is None:
        return None
    if isinstance(doc, list):
        return [_serialize(d) for d in doc]
    if isinstance(doc, dict):
        result = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                result[k] = str(v)
            elif hasattr(v, 'isoformat'):
                result[k] = v.isoformat()
            elif isinstance(v, dict):
                result[k] = _serialize(v)
            elif isinstance(v, list):
                result[k] = [_serialize(i) for i in v]
            else:
                result[k] = v
        return result
    return doc


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

        cursor = cursor.limit(TIMEOUT_SECONDS)
        results = list(cursor.limit(limit))

        return {"results": _serialize(results), "count": len(results)}
    except Exception as e:
        return {"error": str(e)}


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

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message}
    ]

    # Function calling loop (max 5 iterations to prevent infinite loops)
    for _ in range(5):
        response = client.chat.completions.create(
            model=OPENCODE_MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto"
        )

        choice = response.choices[0]

        # If no tool call, return the text response
        if not choice.message.tool_calls:
            return choice.message.content or "I couldn't process your request."

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
                # Convert string params to appropriate types
                func_def = FUNCTIONS.get(func_name, {})
                converted_args = {}
                for k, v in func_args.items():
                    if isinstance(v, str):
                        # Try to convert to proper types
                        if k.endswith("_id") and len(v) == 24:
                            converted_args[k] = v  # Keep as string, handler will convert
                        elif v.isdigit():
                            converted_args[k] = int(v)
                        elif v.replace(".", "").isdigit():
                            converted_args[k] = float(v)
                        else:
                            converted_args[k] = v
                    else:
                        converted_args[k] = v

                result = execute_function(func_name, converted_args, user_role)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=str)
            })

    # If we've exceeded iterations, return what we have
    return "I processed your request but needed more steps. Please try a simpler query."
