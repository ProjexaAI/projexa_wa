from pymongo.collection import Collection
from agent.db import get_collection


ROLE_PERMISSIONS = {
    "ADMIN": {
        "read": "*",  # all collections
        "write": "*"
    },
    "PLACEMENT_COORDINATOR": {
        "read": [
            "users", "studenttrackenrollments", "enrollmentmentorassignments",
            "studentattendances", "tracks", "tracksessionconfigs",
            "mentorstudentinteractions", "mentorinteractionsessions",
            "studentprogresses", "mentorevaluationscores",
            "announcements"
        ],
        "write": [
            "studentattendances", "mentorstudentinteractions",
            "mentorinteractionsessions", "mentorevaluationscores",
            "studentprogresses"
        ]
    },
    "MENTOR": {
        "read": [
            "users", "studenttrackenrollments", "enrollmentmentorassignments",
            "studentattendances", "tracks", "tracksessionconfigs",
            "mentorstudentinteractions", "mentorinteractionsessions",
            "studentprogresses", "mentorevaluationscores",
            "announcements"
        ],
        "write": [
            "studentattendances", "mentorstudentinteractions",
            "mentorinteractionsessions", "mentorevaluationscores",
            "studentprogresses"
        ]
    },
    "STUDENT": {
        "read": [
            "users", "tracks", "tracksessionconfigs", "studenttrackenrollments",
            "studentattendances", "mentorstudentinteractions",
            "enrollmentmentorassignments", "enrollmentscoreledgers",
            "trackonboardingsubmissions", "mentorinteractionsessions",
            "mentorevaluationscores", "trackevaluationevents",
            "announcements", "teams", "teaminvitations"
        ],
        "write": [
            "teams", "teaminvitations"
        ]
    }
}


def get_user_by_phone(phone: str) -> dict | None:
    import re
    import logging
    logger = logging.getLogger("webhook")

    # Strip @lid or @c.us suffixes
    clean_phone = phone.replace("@lid", "").replace("@c.us", "")
    digits_only = re.sub(r"[^0-9]", "", clean_phone)

    logger.info(f"[USER_LOOKUP] Input: phone={phone}, clean={clean_phone}, digits={digits_only}")

    # Match filter: isActive=True, isDeleted is False OR null/undefined
    match_filter = {
        "isActive": True,
        "$or": [
            {"isDeleted": False},
            {"isDeleted": {"$exists": False}},
            {"isDeleted": None}
        ]
    }

    # 1. Exact match (clean)
    user = get_collection("users").find_one(
        {**match_filter, "mobileNumber": clean_phone},
        {"_id": 1, "name": 1, "email": 1, "roles": 1, "mobileNumber": 1}
    )
    if user:
        logger.info(f"[USER_LOOKUP] Found by exact match: {clean_phone}")
        return user

    # 2. Exact match (digits only)
    if digits_only != clean_phone:
        user = get_collection("users").find_one(
            {**match_filter, "mobileNumber": digits_only},
            {"_id": 1, "name": 1, "email": 1, "roles": 1, "mobileNumber": 1}
        )
        if user:
            logger.info(f"[USER_LOOKUP] Found by digits match: {digits_only}")
            return user

    # 3. Match with country code variations (last 10 digits)
    if len(digits_only) >= 10:
        last10 = digits_only[-10:]
        user = get_collection("users").find_one(
            {**match_filter, "mobileNumber": {"$regex": last10 + "$"}},
            {"_id": 1, "name": 1, "email": 1, "roles": 1, "mobileNumber": 1}
        )
        if user:
            logger.info(f"[USER_LOOKUP] Found by last-10 regex: {last10}")
            return user

    # 4. Debug: show what's actually in DB for this phone pattern
    if len(digits_only) >= 10:
        last10 = digits_only[-10:]
        sample = get_collection("users").find(
            {"mobileNumber": {"$regex": last10}},
            {"_id": 0, "mobileNumber": 1, "isActive": 1, "isDeleted": 1}
        ).limit(5)
        for s in sample:
            logger.info(f"[USER_LOOKUP] DB candidate: {s}")

    logger.warning(f"[USER_LOOKUP] No user found for: {phone}")
    return None


def can_read(user_role: str, collection: str) -> bool:
    perms = ROLE_PERMISSIONS.get(user_role, {})
    allowed = perms.get("read", [])
    if allowed == "*":
        return True
    return collection in allowed


def can_write(user_role: str, collection: str) -> bool:
    perms = ROLE_PERMISSIONS.get(user_role, {})
    allowed = perms.get("write", [])
    if allowed == "*":
        return True
    return collection in allowed


def get_allowed_collections(user_role: str) -> dict:
    perms = ROLE_PERMISSIONS.get(user_role, {})
    return {
        "read": perms.get("read", []),
        "write": perms.get("write", [])
    }
