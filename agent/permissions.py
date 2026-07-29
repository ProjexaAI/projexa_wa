from pymongo.collection import Collection
from agent.db import get_collection


ROLE_PERMISSIONS = {
    "ADMIN": {
        "read": "*",  # all collections
        "write": "*"
    },
    "MENTOR": {
        "read": [
            "users", "studenttrackenrollments", "enrollmentmentorassignments",
            "studentattendances", "tracks", "tracksessionconfigs",
            "mentorstudentinteractions", "mentorinteractionsessions",
            "studentprogresses", "mentorevaluationscores",
            "notifications", "announcements"
        ],
        "write": [
            "studentattendances", "mentorstudentinteractions",
            "mentorinteractionsessions", "mentorevaluationscores",
            "studentprogresses", "notifications"
        ]
    },
    "STUDENT": {
        "read": [
            "users", "tracks", "tracksessionconfigs", "studenttrackenrollments",
            "studentattendances", "mentorstudentinteractions",
            "enrollmentmentorassignments", "enrollmentscoreledgers",
            "notifications", "announcements", "teams", "teaminvitations"
        ],
        "write": [
            "teams", "teaminvitations"
        ]
    }
}


def get_user_by_phone(phone: str) -> dict | None:
    # Strip @lid or @c.us suffixes
    clean_phone = phone.replace("@lid", "").replace("@c.us", "")

    # Try exact match first
    user = get_collection("users").find_one(
        {"mobileNumber": clean_phone, "isActive": True, "isDeleted": False},
        {"_id": 1, "name": 1, "email": 1, "roles": 1, "mobileNumber": 1}
    )
    if user:
        return user

    # Try with @lid suffix (WhatsApp LID format)
    user = get_collection("users").find_one(
        {"mobileNumber": phone, "isActive": True, "isDeleted": False},
        {"_id": 1, "name": 1, "email": 1, "roles": 1, "mobileNumber": 1}
    )
    if user:
        return user

    # Try regex match (e.g., user stored as "+919876543210" or "91-9876543210")
    import re
    digits_only = re.sub(r"[^0-9]", "", clean_phone)
    if len(digits_only) >= 10:
        # Match last 10 digits to handle country code variations
        user = get_collection("users").find_one(
            {"mobileNumber": {"$regex": digits_only[-10:] + "$"}, "isActive": True, "isDeleted": False},
            {"_id": 1, "name": 1, "email": 1, "roles": 1, "mobileNumber": 1}
        )
        if user:
            return user

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
