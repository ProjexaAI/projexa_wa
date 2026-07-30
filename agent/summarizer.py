import json
from config import OPENCODE_API_KEY, OPENCODE_MODEL, OPENCODE_BASE_URL
from openai import OpenAI

client = OpenAI(api_key=OPENCODE_API_KEY, base_url=OPENCODE_BASE_URL)

SIZE_THRESHOLD = 2000
MAX_SUMMARY_CHARS = 500
SUMMARY_TIMEOUT = 3

# Intent inference: function name → what the agent is trying to accomplish
INTENT_MAP = {
    "get_student_mentor": "mentor lookup",
    "get_mentor_assignments": "mentor assignments",
    "assign_student_to_mentor": "mentor assignment",
    "release_mentor_assignment": "release mentor",
    "get_student_enrollments": "enrollment details",
    "list_enrollments": "enrollment listing",
    "get_enrollment": "enrollment details",
    "list_teams": "team listing",
    "get_team": "team details",
    "create_team": "create team",
    "join_team": "join team",
    "list_interactions": "interaction history",
    "get_interaction": "interaction details",
    "create_interaction": "create interaction",
    "get_attendance_stats": "attendance check",
    "get_score_ledger": "marks/scores",
    "get_marks_hierarchy": "marks hierarchy",
    "list_users": "user search",
    "get_user_by_id": "user details",
    "list_notifications": "notifications",
    "list_announcements": "announcements",
    "get_onboarding_status": "onboarding status",
    "get_submissions": "submissions",
    "execute_mongodb_query": "custom query"
}

# Keyword patterns to extract intent from conversation context
INTENT_KEYWORDS = {
    "mentor": ["mentor", "assigned", "guide", "instructor"],
    "enrollment": ["enrollment", "enrolled", "track", "program"],
    "team": ["team", "group", "member"],
    "attendance": ["attendance", "present", "absent", "class"],
    "marks": ["marks", "score", "grade", "evaluation"],
    "interaction": ["interaction", "session", "meeting", "call"],
    "notification": ["notification", "alert", "message"],
    "announcement": ["announcement", "update", "news"],
    "onboarding": ["onboarding", "submission", "form"]
}

# Function-specific field extraction rules
# "keep" = always include these fields (top-level)
# "flatten" = extract nested fields into summary
# "drop" = never include
FUNCTION_RULES = {
    "get_student_mentor": {
        "keep": ["assigned", "source"],
        "nested_keep": {
            "mentor": ["name", "email", "mobileNumber"]
        }
    },
    "get_mentor_assignments": {
        "keep": ["assigned", "source"],
        "nested_keep": {
            "assignment": ["enrollmentId", "assignedAt", "isActive"],
            "mentor": ["name", "email"]
        }
    },
    "list_teams": {
        "keep": ["name", "status", "trackSessionConfigId"],
        "item_fields": ["name", "status"],
        "count_label": "teams"
    },
    "list_enrollments": {
        "item_fields": ["status", "section", "startedAt"],
        "count_label": "enrollments"
    },
    "get_student_enrollments": {
        "item_fields": ["status", "section", "startedAt"],
        "count_label": "enrollments"
    },
    "list_interactions": {
        "item_fields": ["title", "status", "createdAt"],
        "count_label": "interactions"
    },
    "list_users": {
        "keep": ["items", "total", "page", "pageSize"],
        "item_fields": ["name", "email", "roles"],
        "count_label": "users"
    },
    "get_attendance_stats": {
        "keep": ["totalClasses", "attended", "percentage"]
    },
    "get_score_ledger": {
        "item_fields": ["trackName", "score", "maxScore"],
        "count_label": "scores"
    },
    "get_marks_hierarchy": {
        "item_fields": ["trackName", "totalScore"],
        "count_label": "tracks"
    },
    "list_notifications": {
        "keep": ["items", "total", "page", "pageSize"],
        "item_fields": ["title", "message", "status", "createdAt"],
        "count_label": "notifications"
    },
    "list_announcements": {
        "keep": ["items", "total", "page", "pageSize"],
        "item_fields": ["title", "message", "audience", "trackScope", "status", "readAt", "recipientRole", "createdAt"],
        "count_label": "announcements"
    },
    "list_tracks": {
        "keep": ["items", "total", "page", "pageSize"],
        "item_fields": ["name", "type", "createdAt"],
        "count_label": "tracks"
    },
    "execute_mongodb_query": {
        "item_fields": [],
        "count_label": "results"
    }
}


def _json_size(data) -> int:
    return len(json.dumps(data, default=str))


def _build_intent(function_name: str, conversation_context: str, user_message: str) -> str:
    """
    Build a short intent string from function name, conversation context, and user message.
    This helps the summarizer understand what the agent is trying to accomplish.
    """
    # Primary: use INTENT_MAP for known functions
    base_intent = INTENT_MAP.get(function_name, "data lookup")

    # Enhance with conversation context keywords
    context_lower = (conversation_context or "").lower()
    user_lower = (user_message or "").lower()
    combined = f"{context_lower} {user_lower}"

    # Check for specific intent keywords in context
    for intent_key, keywords in INTENT_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return f"{base_intent} ({intent_key} context)"

    # Check for confirmation patterns (user saying yes/ok/sure)
    confirmations = ["yes", "ok", "sure", "go ahead", "do it", "confirm", "yeah", "yep"]
    if any(user_lower.strip().startswith(c) for c in confirmations):
        return f"{base_intent} (user confirmed previous request)"

    # Check for negation patterns
    negations = ["no", "cancel", "nevermind", "stop", "don't"]
    if any(user_lower.strip().startswith(n) for n in negations):
        return f"{base_intent} (user cancelled/negated)"

    return base_intent


def _apply_rules(data: dict, rules: dict) -> dict:
    """Apply function-specific extraction rules to reduce payload size."""
    if not isinstance(data, dict):
        return data

    result = {}

    # Keep top-level fields
    for field in rules.get("keep", []):
        if field in data:
            result[field] = data[field]

    # Extract nested fields
    for parent_field, child_fields in rules.get("nested_keep", {}).items():
        if parent_field in data and isinstance(data[parent_field], dict):
            result[parent_field] = {
                k: v for k, v in data[parent_field].items()
                if k in child_fields
            }

    return result


def _summarize_items(data: list, rules: dict) -> dict:
    """Summarize a list of items by extracting key fields."""
    item_fields = rules.get("item_fields", [])
    count_label = rules.get("count_label", "records")

    if not item_fields:
        # No specific fields — just return count
        return {"total": len(data), "type": count_label}

    # Show all items if ≤ 20, else cap at 10
    max_items = len(data) if len(data) <= 20 else 10
    summary_items = []
    for item in data[:max_items]:
        if isinstance(item, dict):
            summary_items.append({
                k: v for k, v in item.items()
                if k in item_fields or k == "_id"
            })

    return {
        "total": len(data),
        "type": count_label,
        "items": summary_items,
        "truncated": len(data) > max_items
    }


def summarize_result(
    raw_result: dict,
    function_name: str,
    function_params: dict,
    user_message: str,
    conversation_context: str = ""
) -> str:
    """
    Summarize a raw query result based on function context and conversation history.

    Args:
        raw_result: The raw MongoDB query result
        function_name: Name of the function that was called
        function_params: Parameters passed to the function
        user_message: The original user message for context
        conversation_context: Recent conversation messages for intent inference

    Returns:
        A condensed string summary of the result
    """
    # Build intent from all available context
    intent = _build_intent(function_name, conversation_context, user_message)

    # Handle error results
    if isinstance(raw_result, dict) and "error" in raw_result:
        return json.dumps(raw_result, default=str)

    # Check size — skip summarization for small results
    size = _json_size(raw_result)
    if size <= SIZE_THRESHOLD:
        return json.dumps(raw_result, default=str)

    rules = FUNCTION_RULES.get(function_name, {})

    # Apply function-specific rules
    if isinstance(raw_result, dict) and rules:
        reduced = _apply_rules(raw_result, rules)
        if reduced and _json_size(reduced) <= MAX_SUMMARY_CHARS:
            return json.dumps(reduced, default=str)

    # Handle list results
    if isinstance(raw_result, list):
        if rules.get("item_fields"):
            summary = _summarize_items(raw_result, rules)
            return json.dumps(summary, default=str)
        # No specific rules — summarize generically
        summary = {
            "total": len(raw_result),
            "sample": raw_result[:3] if raw_result else [],
            "truncated": len(raw_result) > 3
        }
        if _json_size(summary) <= MAX_SUMMARY_CHARS:
            return json.dumps(summary, default=str)

    # Handle dict with "items" or "results" key (paginated/custom query results)
    if isinstance(raw_result, dict) and ("items" in raw_result or "results" in raw_result):
        items = raw_result.get("items") or raw_result.get("results", [])
        total = raw_result.get("total") or raw_result.get("count", len(items))
        if rules.get("item_fields"):
            max_items = len(items) if len(items) <= 20 else 10
            summary_items = []
            for item in items[:max_items]:
                if isinstance(item, dict):
                    summary_items.append({
                        k: v for k, v in item.items()
                        if k in rules["item_fields"] or k == "_id"
                    })
            summary = {
                "total": total,
                "type": rules.get("count_label", "records"),
                "items": summary_items,
                "truncated": total > max_items
            }
        else:
            # Generic summarization for items without specific rules
            max_items = len(items) if len(items) <= 20 else 10
            summary_items = []
            for item in items[:max_items]:
                if isinstance(item, dict):
                    summary_items.append(item)
                else:
                    summary_items.append(item)
            summary = {
                "total": total,
                "type": rules.get("count_label", "records"),
                "items": summary_items,
                "truncated": total > max_items
            }
        return json.dumps(summary, default=str)

    # Last resort: LLM summarization for large payloads
    if size > SIZE_THRESHOLD:
        return _llm_summarize(raw_result, function_name, user_message, intent, conversation_context)

    return json.dumps(raw_result, default=str)


def _llm_summarize(data: dict, function_name: str, user_message: str,
                   intent: str = "", conversation_context: str = "") -> str:
    """Use LLM to summarize large results that don't fit rules."""
    data_str = json.dumps(data, default=str)[:3000]  # Cap input

    # Build context snippet from recent conversation
    context_snippet = ""
    if conversation_context:
        context_snippet = f"\nRecent conversation:\n{conversation_context[:500]}"

    prompt = f"""Summarize this database query result for a WhatsApp chatbot response.

Intent: {intent}
User's latest message: "{user_message}"{context_snippet}

Rules:
- Max 500 characters
- Use bullet points
- Include only the key information the user needs
- Drop internal IDs, timestamps, metadata
- If it's a list, show total count and first few items
- Match the intent: if looking for a mentor, show name/contact; if looking for enrollments, show track/status

Data:
{data_str}

Summary:"""

    try:
        response = client.chat.completions.create(
            model=OPENCODE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.1
        )
        return response.choices[0].content or data_str[:MAX_SUMMARY_CHARS]
    except Exception:
        # Fallback: truncate raw data
        return data_str[:MAX_SUMMARY_CHARS] + "... (truncated)"
