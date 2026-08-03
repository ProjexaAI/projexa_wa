"""
Intent detection for dynamic context loading.

Classifies user messages into intent categories to determine which
schemas, function docs, and tools to include in the AI prompt.
This reduces context bloat by ~60%.

Detection priority:
1. Domain keyword matching (fast, free)
2. Follow-up pattern detection + history carryover
3. LLM fallback (when available)
4. General intent (greetings, help, unknown)
"""

import re
import logging

logger = logging.getLogger("webhook")


# ============================================================
# INTENT DEFINITIONS
# ============================================================

INTENTS = {
    "general": {
        "keywords": [],
        "schemas": ["core.md"],
        "function_docs": ["auth-functions.md"],
        "tools": [
            "get_user_by_id", "get_current_session",
            "list_announcements", "list_tracks",
        ],
    },
    "profile": {
        "keywords": [
            "photo", "photos", "picture", "pictures", "image", "images",
            "profile photo", "profile picture", "profile image",
            "my photo", "my picture", "my image", "my profile",
            "avatar", "display picture", "dp",
        ],
        "schemas": ["core.md"],
        "function_docs": ["user-functions.md", "auth-functions.md"],
        "tools": [
            "get_user_by_id", "send_media", "get_current_session",
        ],
    },
    "user_info": {
        "keywords": [
            "user", "profile", "account", "my info", "my details",
            "who am i", "my name", "my email", "my role",
            "list users", "all users", "find user", "search user",
            "update user", "edit user", "change user",
            "info on", "info about", "details on", "details about",
            "tell me about", "who is", "who's", "what do you know about",
            "give me info", "give me details", "get user",
            "find", "search", "lookup", "look up",
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
    # Follow-up intent: loaded when message is a follow-up reference
    # Contains a superset of tools for common follow-up actions
    "followup": {
        "keywords": [],
        "schemas": [
            "core.md", "attendance.md", "evaluation.md", "mentor.md",
            "teams.md", "notifications.md", "onboarding.md",
        ],
        "function_docs": [
            "auth-functions.md", "announcement-functions.md",
            "attendance-functions.md", "enrollment-functions.md",
            "evaluation-functions.md", "mentor-functions.md",
            "onboarding-functions.md", "team-functions.md",
            "track-functions.md", "user-functions.md",
        ],
        "tools": [
            # Announcements (common follow-up target)
            "list_announcements", "get_announcement",
            "get_announcement_attachments", "mark_announcement_read",
            # Enrollment
            "get_enrollment", "get_student_enrollments",
            # Attendance
            "get_student_attendance", "get_attendance_stats",
            "get_student_attendance_detail",
            # Evaluation
            "get_score_ledger", "get_student_score_summary",
            "get_marks_hierarchy",
            # Mentor
            "get_student_mentor", "list_interactions",
            "get_interaction", "get_student_interactions_detail",
            # Onboarding
            "get_onboarding_status", "get_submissions",
            "get_student_documents", "get_student_document_summary",
            # Teams
            "list_teams", "get_team",
            # User
            "get_user_by_id",
            # Session
            "get_current_session",
            # Always available
            "execute_mongodb_query", "send_media",
        ],
    },
}

# Intents that are always included
_ALWAYS_RELEVANT = {"session"}


# ============================================================
# FOLLOW-UP PATTERN DETECTION
# ============================================================

# Patterns that indicate a follow-up reference (not a new topic)
_FOLLOWUP_PATTERNS = [
    # Numbered references: "1st", "2nd", "#1", "#2"
    r'^\d{1,2}(?:st|nd|rd|th)$',
    r'^#\d{1,2}$',
    # Ordinal words: "first", "second", "third"
    r'^(?:first|second|third|fourth|fifth|last|latest|previous)$',
    # Number words: "one", "two", "three"
    r'^(?:one|two|three|four|five|both|all|none|neither)$',
    # Pronoun + reference patterns
    r'^(?:the\s+)?(?:that|this|it|them|those)\s*(?:one|time|thing)?$',
    r'^(?:send|show|open|download|share|get)\s+(?:it|them|that|this|the\s+file)',
    # Confirmation/denial (very short, no domain keywords)
    r'^(?:yes|no|yeah|nope|yep|nah|ok|okay|sure|please|thanks|thank you|do it|go ahead|skip|cancel|confirm|done)$',
    # Partial reference: "the attendance one", "the mentor one"
    r'^the\s+\w+\s+one$',
    # Action phrases
    r'^(?:mark|send|show|get|fetch|find|look)\s+(?:it|me|them|that|this)',
]

_COMPILED_FOLLOWUP_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _FOLLOWUP_PATTERNS]

# Words that indicate a NEW topic (not a follow-up)
_NEW_TOPIC_INDICATORS = [
    "show", "list", "get", "find", "search", "create", "add", "update",
    "delete", "remove", "mark", "assign", "release", "submit", "join",
    "what", "how", "when", "where", "who", "why", "can you", "could you",
    "i want", "i need", "help me", "tell me",
]


def _is_followup(message: str) -> bool:
    """
    Detect if a message is a follow-up reference rather than a new topic.
    
    Only matches explicit follow-up patterns: numbered references,
    pronouns, confirmations. Everything else goes to LLM fallback.
    """
    msg = message.strip()
    msg_lower = msg.lower()

    # FIRST: Check if message contains any domain keywords
    # If it has domain keywords, it's NOT a follow-up
    domain_keywords = [
        "attendance", "score", "marks", "evaluation", "mentor", "interaction",
        "team", "enrollment", "document", "submission", "announcement",
        "track", "course", "programme", "session", "user", "profile",
        "photo", "picture", "image", "avatar",
    ]
    for kw in domain_keywords:
        if kw in msg_lower:
            return False

    # SECOND: Only match explicit follow-up patterns
    for pattern in _COMPILED_FOLLOWUP_PATTERNS:
        if pattern.match(msg_lower):
            return True

    return False


# ============================================================
# HISTORY-ASSISTED INTENT DETECTION
# ============================================================

def _carry_intent_from_history(history: list[dict]) -> set[str] | None:
    """
    Check the last assistant response in history to determine what the
    user is referring to with follow-up references.
    
    Returns the relevant intent set if context is found, None otherwise.
    """
    if not history:
        return None

    # Get the last assistant message
    last_assistant = None
    for msg in reversed(history):
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
        if role == "assistant":
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if content:
                last_assistant = content.lower()
            break

    if not last_assistant:
        return None

    # Map keywords in the last response to intents
    intent_signals = {
        "announcements": ["announcement", "announcements", "notice", "broadcast"],
        "attendance": ["attendance", "present", "absent"],
        "evaluation": ["score", "marks", "evaluation", "grading"],
        "mentor": ["mentor", "interaction", "meeting"],
        "teams": ["team", "invite", "member"],
        "enrollment": ["enrollment", "enrolled", "track"],
        "onboarding": ["document", "submission", "onboarding"],
        "tracks": ["track", "course", "programme"],
    }

    for intent, keywords in intent_signals.items():
        for kw in keywords:
            if kw in last_assistant:
                logger.info(f"[INTENT] History context: '{kw}' found -> {intent}")
                return {intent}

    return None


# ============================================================
# KEYWORD-BASED INTENT DETECTION
# ============================================================

def _detect_intents_by_keywords(message: str) -> set[str]:
    """Detect intents from user message using keyword matching."""
    msg_lower = message.lower().strip()
    detected = set()

    # Bare identifier patterns → user_info (no context words needed)
    # Phone number: 10 digits (with or without country code)
    if re.search(r'(?:\+?91)?[\s-]?\d{10}\b', message):
        detected.add("user_info")
    # Email address
    if re.search(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b', message):
        detected.add("user_info")
    # Roll number: "roll" or "rollno" or "roll no" followed by digits
    if re.search(r'\broll\s*(?:no\.?|number)?\s*\d+\b', msg_lower):
        detected.add("user_info")

    for intent, config in INTENTS.items():
        if intent == "followup":
            continue  # Skip followup in keyword matching
        for keyword in config["keywords"]:
            if len(keyword) <= 5:
                if re.search(r'\b' + re.escape(keyword) + r'\b', msg_lower):
                    detected.add(intent)
                    break
            else:
                if keyword in msg_lower:
                    detected.add(intent)
                    break

    return detected


# ============================================================
# LLM-BASED INTENT DETECTION (FALLBACK)
# ============================================================

_INTENT_DETECT_PROMPT = """You are an intent classifier for a WhatsApp chatbot. Classify the user's message.

INTENTS:
- user_info: Looking up any user by name, email, phone, roll number, or any identifier. Also includes "who is X", "tell me about X", "info on X", "find X", "search X", profile queries, listing users.
- tracks: Track listing, course details, programme info, track configs.
- enrollment: Enrollment status, enrollment listing, enrollment updates.
- attendance: Attendance marking, stats, records, present/absent.
- evaluation: Scores, marks, grades, evaluations, score ledger.
- mentor: Mentor assignments, mentor interactions, student progress, meetings.
- teams: Team creation, joining, invitations, team members.
- announcements: Announcements, notices, notifications, broadcasts.
- onboarding: Document submissions, intake forms, document status, uploads.
- session: Academic year, current session, active session.
- general: Greetings, help requests, capabilities, casual chat, off-topic.

RULES:
- A bare name like "rahul" or "john" → user_info
- A bare email → user_info
- A bare phone number → user_info
- A roll number → user_info
- "what about X" or "who is X" → user_info
- Greetings like "hello", "hi", "hey" → general
- "help", "what can you do" → general

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
                {"role": "system", "content": "You are an intent classifier. You MUST return only comma-separated intent names. No explanations. No reasoning. Just the intent names."},
                {"role": "user", "content": _INTENT_DETECT_PROMPT.format(message=message, role=user_role)},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        choice = response.choices[0]
        raw = choice.message.content
        if not raw or not raw.strip():
            logger.warning(f"[INTENT] LLM returned empty content (finish_reason={choice.finish_reason})")
            return {"general"}
        raw = raw.strip().lower()
        intents = set()
        for part in raw.split(","):
            part = part.strip().strip('"').strip("'")
            if part in INTENTS:
                intents.add(part)
        return intents if intents else {"general"}
    except Exception as e:
        logger.warning(f"[INTENT] LLM detection failed: {e}")
        return {"general"}


# ============================================================
# PUBLIC API
# ============================================================

def detect_intents(message: str, user_role: str = None, client=None, model: str = None,
                    history: list[dict] = None) -> set[str]:
    """
    Detect user intents from a message.
    
    Detection priority:
    1. Follow-up pattern matching (fast, free)
    2. Domain keyword matching (fast, free) for obvious queries
    3. LLM fallback for everything else (names, ambiguous queries, etc.)
    
    Always includes 'session' intent for context.
    """
    # Step 1: Check if this is a follow-up reference (before keyword matching)
    if _is_followup(message):
        carried = _carry_intent_from_history(history)
        if carried:
            carried.add("session")
            logger.info(f"[INTENT] Follow-up with history context: {carried}")
            return carried
        followup_intents = {"followup", "session"}
        logger.info(f"[INTENT] Follow-up without history context: using followup superset")
        return followup_intents

    # Step 2: Try domain keyword matching
    intents = _detect_intents_by_keywords(message)
    if intents:
        intents.add("session")
        logger.info(f"[INTENT] Keywords detected: {intents}")
        return intents

    # Step 3: LLM fallback (handles names, ambiguous queries, greetings, etc.)
    if client and model:
        logger.info("[INTENT] No keywords matched, using LLM fallback")
        intents = _detect_intents_by_llm(message, user_role, client, model)
        intents.add("session")
        logger.info(f"[INTENT] LLM detected: {intents}")
        return intents

    # Step 4: Minimal context
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
    """Check if full context is needed (empty intents)."""
    return len(intents) == 0
