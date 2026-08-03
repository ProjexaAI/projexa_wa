"""
Intent detection for dynamic context loading.

Classifies user messages into intent categories to determine which
schemas, function docs, and tools to include in the AI prompt.
This reduces context bloat by ~60%.
"""

import re
import logging

logger = logging.getLogger("webhook")


# ============================================================
# INTENT DEFINITIONS
# ============================================================

INTENTS = {
    "general": {
        "keywords": [],  # Only triggered by fallback (greetings, help)
        "schemas": ["core.md"],
        "function_docs": ["auth-functions.md"],
        "tools": [
            "get_user_by_id", "get_current_session",
            "list_announcements", "list_tracks",
        ],
    },
    "user_info": {
        "keywords": [
            "user", "profile", "account", "my info", "my details",
            "who am i", "my name", "my email", "my role",
            "list users", "all users", "find user", "search user",
            "update user", "edit user", "change user",
        ],
        "schemas": ["core.md"],
        "function_docs": ["user-functions.md", "auth-functions.md"],
        "tools": [
            "get_user_by_id", "get_user_by_email", "list_users", "update_user",
        ],
    },
    "tracks": {
        "keywords": [
            "track", "tracks", "course", "programme", "program",
            "web dev", "ai", "data science", "cyber", "blockchain",
            "list tracks", "all tracks", "track list",
            "track config", "session config", "track detail",
        ],
        "schemas": ["core.md"],
        "function_docs": ["track-functions.md", "auth-functions.md"],
        "tools": [
            "list_tracks", "get_track", "get_track_by_code",
            "list_track_configs", "get_track_config", "get_track_config_by_id",
        ],
    },
    "enrollment": {
        "keywords": [
            "enrollment", "enrolment", "enrolled", "enroll",
            "my track", "my course", "my programme",
            "active", "inactive", "completed",
            "register", "admission", "status",
        ],
        "schemas": ["core.md"],
        "function_docs": ["enrollment-functions.md", "auth-functions.md"],
        "tools": [
            "list_enrollments", "get_enrollment", "get_student_enrollments",
            "update_enrollment_status",
        ],
    },
    "attendance": {
        "keywords": [
            "attendance", "present", "absent", "attendance%",
            "mark attendance", "attendance record", "attendance stats",
            "attendance detail", "attendance summary",
        ],
        "schemas": ["attendance.md", "core.md"],
        "function_docs": ["attendance-functions.md"],
        "tools": [
            "mark_attendance", "get_student_attendance", "get_session_attendance",
            "get_attendance_stats", "get_student_attendance_detail",
        ],
    },
    "evaluation": {
        "keywords": [
            "score", "marks", "grade", "evaluation", "scoring",
            "ledger", "hierarchy", "evaluation score",
            "submit evaluation", "record score", "add marks",
            "my marks", "my scores", "score summary",
        ],
        "schemas": ["evaluation.md"],
        "function_docs": ["evaluation-functions.md"],
        "tools": [
            "get_score_ledger", "record_score", "get_mentor_eval_scores",
            "submit_mentor_evaluation", "get_marks_hierarchy",
            "get_student_score_summary",
        ],
    },
    "mentor": {
        "keywords": [
            "mentor", "mentors", "my mentor", "who is my mentor",
            "mentor assign", "assign mentor", "release mentor",
            "interaction", "interactions", "mentor interaction",
            "student progress", "progress",
        ],
        "schemas": ["mentor.md"],
        "function_docs": ["mentor-functions.md"],
        "tools": [
            "get_mentor_assignments", "get_student_mentor",
            "assign_student_to_mentor", "release_mentor_assignment",
            "list_interactions", "get_interaction", "create_interaction",
            "update_interaction", "finalize_interaction",
            "get_student_progress", "get_student_interactions_detail",
        ],
    },
    "teams": {
        "keywords": [
            "team", "teams", "my team", "join team", "create team",
            "team invite", "invitation", "invite code",
            "team member", "leader", "team list",
        ],
        "schemas": ["teams.md"],
        "function_docs": ["team-functions.md"],
        "tools": [
            "list_teams", "get_team", "create_team", "join_team",
            "invite_to_team", "respond_to_invitation",
        ],
    },
    "announcements": {
        "keywords": [
            "announcement", "announcements", "notice", "notices",
            "notification", "broadcast", "news", "update",
            "new announcement", "create announcement",
            "attachment", "attachments",
        ],
        "schemas": ["notifications.md"],
        "function_docs": ["announcement-functions.md"],
        "tools": [
            "list_announcements", "get_announcement",
            "get_announcement_attachments", "create_announcement",
            "mark_announcement_read",
        ],
    },
    "onboarding": {
        "keywords": [
            "document", "documents", "upload", "submission", "submit",
            "intake", "intake form", "onboarding", "doc status",
            "document status", "pending documents", "approved",
            "rejected", "document upload",
        ],
        "schemas": ["onboarding.md"],
        "function_docs": ["onboarding-functions.md"],
        "tools": [
            "get_onboarding_status", "get_submissions", "submit_intake_form",
            "get_student_documents", "get_student_document_summary",
            "submit_document_upload",
        ],
    },
    "session": {
        "keywords": [
            "session", "academic year", "year", "current session",
            "active session", "list sessions",
        ],
        "schemas": ["core.md"],
        "function_docs": ["auth-functions.md"],
        "tools": [
            "get_current_session", "list_academic_years",
        ],
    },
}

# Intents that are always relevant (for greetings, help, general queries)
_ALWAYS_RELEVANT = {"session", "general"}

# Fallback keywords for when primary keyword matching finds nothing
# These help classify vague/greeting messages without needing an LLM call
_FALLBACK_KEYWORDS = {
    "greeting": ["hello", "hi", "hey", "good morning", "good evening",
                 "how are you", "what's up", "sup", "yo"],
    "help": ["help", "what can you do", "what do you do", "capabilities",
             "features", "options", "menu"],
}


# ============================================================
# KEYWORD-BASED INTENT DETECTION
# ============================================================

def _detect_intents_by_keywords(message: str) -> set[str]:
    """Detect intents from user message using keyword matching.
    
    Uses word boundary matching for short keywords (<=5 chars) to avoid
    false positives (e.g., 'hello' matching inside 'enrollment').
    Uses substring matching for longer keywords.
    """
    msg_lower = message.lower().strip()
    detected = set()

    for intent, config in INTENTS.items():
        for keyword in config["keywords"]:
            if len(keyword) <= 5:
                # Short keyword: use word boundary matching
                if re.search(r'\b' + re.escape(keyword) + r'\b', msg_lower):
                    detected.add(intent)
                    break
            else:
                # Long keyword: substring matching is fine
                if keyword in msg_lower:
                    detected.add(intent)
                    break

    return detected


# ============================================================
# LLM-BASED INTENT DETECTION (FALLBACK)
# ============================================================

_INTENT_DETECT_PROMPT = """Classify this WhatsApp message into one or more intent categories.

INTENTS:
- user_info: Getting/updating user profile, listing users
- tracks: Track listing, details, configs
- enrollment: Enrollment status, listing, updates
- attendance: Attendance marking, stats, records
- evaluation: Scores, marks, evaluations
- mentor: Mentor assignments, interactions, progress
- teams: Team creation, joining, invitations
- announcements: Announcements, notifications
- onboarding: Document submissions, intake forms
- session: Academic year/session info

MESSAGE: {message}

ROLE: {role}

Return ONLY a comma-separated list of intent names. Example: "attendance,evaluation"
If unclear, return "general"."""


def _detect_intents_by_llm(message: str, user_role: str, client, model: str) -> set[str]:
    """Use a lightweight LLM call to detect intents when keywords fail."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an intent classifier. Return only comma-separated intent names."},
                {"role": "user", "content": _INTENT_DETECT_PROMPT.format(message=message, role=user_role)},
            ],
            temperature=0.0,
            max_tokens=50,
        )
        raw = response.choices[0].message.content.strip().lower()
        intents = set()
        for part in raw.split(","):
            part = part.strip().strip('"').strip("'")
            if part in INTENTS:
                intents.add(part)
        return intents if intents else _ALWAYS_RELEVANT
    except Exception as e:
        logger.warning(f"[INTENT] LLM detection failed: {e}")
        return _ALWAYS_RELEVANT


# ============================================================
# PUBLIC API
# ============================================================

def detect_intents(message: str, user_role: str = None, client=None, model: str = None) -> set[str]:
    """
    Detect user intents from a message.
    
    Uses keyword matching first (fast, free). Falls back to LLM if
    no keywords match and LLM client is provided.
    
    Always includes 'session' intent for context.
    """
    intents = _detect_intents_by_keywords(message)

    # If keywords found something, use it
    if intents:
        intents.add("session")  # Always include session for context
        logger.info(f"[INTENT] Keywords detected: {intents}")
        return intents

    # Check fallback keywords for vague messages
    msg_lower = message.lower().strip()
    for category, keywords in _FALLBACK_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                logger.info(f"[INTENT] Fallback matched: {category} (keyword: {kw})")
                intents.add("session")
                intents.add("general")
                return intents  # Return minimal intents for greetings/help

    # Fallback to LLM if available
    if client and model:
        logger.info("[INTENT] No keywords matched, using LLM fallback")
        intents = _detect_intents_by_llm(message, user_role, client, model)
        intents.add("session")
        logger.info(f"[INTENT] LLM detected: {intents}")
        return intents

    # No detection method available — return minimal context (session only)
    logger.info("[INTENT] No match, using minimal context")
    return _ALWAYS_RELEVANT.copy()


def get_relevant_schemas(intents: set[str]) -> list[str]:
    """Get unique schema files relevant to the detected intents."""
    schemas = set()
    for intent in intents:
        if intent in INTENTS:
            schemas.update(INTENTS[intent]["schemas"])
    return sorted(schemas)


def get_relevant_function_docs(intents: set[str]) -> list[str]:
    """Get unique function doc files relevant to the detected intents."""
    docs = set()
    for intent in intents:
        if intent in INTENTS:
            docs.update(INTENTS[intent]["function_docs"])
    return sorted(docs)


def get_relevant_tools(intents: set[str]) -> list[str]:
    """Get unique tool names relevant to the detected intents."""
    tools = set()
    for intent in intents:
        if intent in INTENTS:
            tools.update(INTENTS[intent]["tools"])
    # Always include execute_mongodb_query and send_media
    tools.add("execute_mongodb_query")
    tools.add("send_media")
    return sorted(tools)


def is_full_context_needed(intents: set[str]) -> bool:
    """Check if the intents are too vague and full context is needed.
    
    Returns False for greetings/help (general intent) since they have
    their own minimal tool set. Only returns True when detection completely
    fails (empty intents).
    """
    return len(intents) == 0
