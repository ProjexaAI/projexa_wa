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
    user = get_collection("users").find_one(
        {"mobileNumber": phone, "isActive": True, "isDeleted": False},
        {"_id": 1, "name": 1, "email": 1, "roles": 1, "mobileNumber": 1}
    )
    return user


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
