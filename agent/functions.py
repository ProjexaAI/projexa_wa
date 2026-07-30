from datetime import datetime
from agent.db import get_collection
from bson import ObjectId
import time

# Simple in-memory cache: {cache_key: {"data": ..., "timestamp": float}}
_CACHE: dict[str, dict] = {}
_CACHE_TTL = 300  # 5 minutes


def _get_cache(key: str):
    """Get cached data if still valid."""
    entry = _CACHE.get(key)
    if entry and time.time() - entry["timestamp"] < _CACHE_TTL:
        return entry["data"]
    return None


def _set_cache(key: str, data):
    """Cache data with timestamp."""
    _CACHE[key] = {"data": data, "timestamp": time.time()}
    # Prune old entries if cache grows too large
    if len(_CACHE) > 200:
        oldest = sorted(_CACHE.keys(), key=lambda k: _CACHE[k]["timestamp"])[:100]
        for k in oldest:
            del _CACHE[k]


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
                    elif isinstance(v, datetime):
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


# ============================================================
# USER FUNCTIONS
# ============================================================

def get_user_by_id(user_id: str) -> dict:
    cache_key = f"user:{user_id}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached
    result = _serialize(get_collection("users").find_one({"_id": ObjectId(user_id)}))
    if result:
        _set_cache(cache_key, result)
    return result


def get_user_by_email(email: str) -> dict:
    return _serialize(get_collection("users").find_one({"email": email.lower()}))


def list_users(role: str = None, search: str = None, page: int = 1, page_size: int = 20) -> dict:
    query = {"isDeleted": False, "isActive": True}
    if role:
        query["roles"] = role
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"rollNumber": {"$regex": search, "$options": "i"}}
        ]
    total = get_collection("users").count_documents(query)
    skip = (page - 1) * page_size
    items = list(get_collection("users").find(query).skip(skip).limit(page_size))
    return {"items": _serialize(items), "total": total, "page": page, "pageSize": page_size}


def update_user(user_id: str, fields: dict) -> dict:
    allowed = {"name", "email", "roles", "mobileNumber", "programme", "section", "studentYear", "isActive"}
    update = {k: v for k, v in fields.items() if k in allowed}
    if not update:
        return {"error": "No valid fields to update"}
    get_collection("users").update_one({"_id": ObjectId(user_id)}, {"$set": update})
    return get_user_by_id(user_id)


# ============================================================
# TRACK FUNCTIONS
# ============================================================

def list_tracks(search: str = None) -> list:
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"code": {"$regex": search, "$options": "i"}}
        ]
    return _serialize(list(get_collection("tracks").find(query).sort("sortOrder", 1)))


def get_track(track_id: str) -> dict:
    return _serialize(get_collection("tracks").find_one({"_id": ObjectId(track_id)}))


def get_track_by_code(code: str) -> dict:
    return _serialize(get_collection("tracks").find_one({"code": code.upper()}))


def list_track_configs(session_id: str = None, search: str = None) -> list:
    query = {"isEnabled": True}
    if session_id:
        query["sessionId"] = ObjectId(session_id)
    configs = list(get_collection("tracksessionconfigs").find(query))
    if search:
        track_ids = [c["trackId"] for c in configs]
        tracks = list(get_collection("tracks").find({"_id": {"$in": track_ids}, "$or": [
            {"name": {"$regex": search, "$options": "i"}},
            {"code": {"$regex": search, "$options": "i"}}
        ]}))
        track_ids_found = {t["_id"] for t in tracks}
        configs = [c for c in configs if c["trackId"] in track_ids_found]
    return _serialize(configs)


def get_track_config(session_id: str, track_id: str) -> dict:
    return _serialize(get_collection("tracksessionconfigs").find_one({
        "sessionId": ObjectId(session_id),
        "trackId": ObjectId(track_id)
    }))


def get_track_config_by_id(config_id: str) -> dict:
    return _serialize(get_collection("tracksessionconfigs").find_one({"_id": ObjectId(config_id)}))


# ============================================================
# ENROLLMENT FUNCTIONS
# ============================================================

def list_enrollments(student_id: str = None, track_config_id: str = None,
                     status: str = None, page: int = 1, page_size: int = 20) -> dict:
    query = {}
    if student_id:
        query["studentId"] = ObjectId(student_id)
    if track_config_id:
        query["trackSessionConfigId"] = ObjectId(track_config_id)
    if status:
        query["status"] = status
    total = get_collection("studenttrackenrollments").count_documents(query)
    skip = (page - 1) * page_size
    items = list(get_collection("studenttrackenrollments").find(query).skip(skip).limit(page_size))
    return {"items": _serialize(items), "total": total, "page": page, "pageSize": page_size}


def get_enrollment(enrollment_id: str) -> dict:
    return _serialize(get_collection("studenttrackenrollments").find_one({"_id": ObjectId(enrollment_id)}))


def get_student_enrollments(student_id: str, session_id: str = None) -> list:
    query = {"studentId": ObjectId(student_id)}
    if session_id:
        query["sessionId"] = ObjectId(session_id)
    return _serialize(list(get_collection("studenttrackenrollments").find(query)))


def update_enrollment_status(enrollment_id: str, status: str, reason: str = None) -> dict:
    valid = ["PENDING_ONBOARDING", "ENROLLED", "ACTIVE", "INACTIVE", "SWITCHED_OUT", "COMPLETED"]
    if status not in valid:
        return {"error": f"Invalid status. Must be one of: {valid}"}
    update = {"status": status}
    if reason:
        update["endedReason"] = reason
    if status in ("INACTIVE", "SWITCHED_OUT", "COMPLETED"):
        update["endedAt"] = datetime.utcnow()
    get_collection("studenttrackenrollments").update_one(
        {"_id": ObjectId(enrollment_id)}, {"$set": update}
    )
    return get_enrollment(enrollment_id)


# ============================================================
# ATTENDANCE FUNCTIONS
# ============================================================

def mark_attendance(enrollment_id: str, date_key: str, status: str, session: str = "MORNING") -> dict:
    if status not in ("PRESENT", "ABSENT"):
        return {"error": "Status must be PRESENT or ABSENT"}
    if session not in ("MORNING", "EVENING"):
        return {"error": "Session must be MORNING or EVENING"}

    enrollment = get_collection("studenttrackenrollments").find_one({"_id": ObjectId(enrollment_id)})
    if not enrollment:
        return {"error": "Enrollment not found"}

    record = {
        "enrollmentId": ObjectId(enrollment_id),
        "studentId": enrollment["studentId"],
        "trackSessionConfigId": enrollment["trackSessionConfigId"],
        "trackId": enrollment.get("trackId"),
        "sessionId": enrollment["sessionId"],
        "dateKey": date_key,
        "attendanceSession": session,
        "status": status,
        "source": "MANUAL",
        "markedAt": datetime.utcnow()
    }

    existing = get_collection("studentattendances").find_one({
        "enrollmentId": ObjectId(enrollment_id),
        "dateKey": date_key,
        "attendanceSession": session
    })
    if existing:
        get_collection("studentattendances").update_one(
            {"_id": existing["_id"]}, {"$set": {"status": status, "markedAt": datetime.utcnow()}}
        )
        record["_id"] = str(existing["_id"])
    else:
        result = get_collection("studentattendances").insert_one(record)
        record["_id"] = str(result.inserted_id)

    return _serialize(record)


def get_student_attendance(student_id: str, session_id: str = None,
                           start_date: str = None, end_date: str = None) -> list:
    query = {"studentId": ObjectId(student_id)}
    if session_id:
        query["sessionId"] = ObjectId(session_id)
    if start_date or end_date:
        query["dateKey"] = {}
        if start_date:
            query["dateKey"]["$gte"] = start_date
        if end_date:
            query["dateKey"]["$lte"] = end_date
    return _serialize(list(get_collection("studentattendances").find(query).sort("dateKey", -1)))


def get_session_attendance(track_config_id: str, date_key: str, session: str = None) -> list:
    query = {"trackSessionConfigId": ObjectId(track_config_id), "dateKey": date_key}
    if session:
        query["attendanceSession"] = session
    return _serialize(list(get_collection("studentattendances").find(query)))


def get_attendance_stats(enrollment_id: str = None, student_id: str = None) -> dict:
    match = {}
    if enrollment_id:
        match["enrollmentId"] = ObjectId(enrollment_id)
    elif student_id:
        match["studentId"] = ObjectId(student_id)
    else:
        return {"error": "Provide enrollment_id or student_id"}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]
    results = list(get_collection("studentattendances").aggregate(pipeline))
    stats = {r["_id"]: r["count"] for r in results}
    total = sum(stats.values())
    present = stats.get("PRESENT", 0)
    return {
        "total": total,
        "present": present,
        "absent": stats.get("ABSENT", 0),
        "percentage": round((present / total * 100), 1) if total > 0 else 0
    }


# ============================================================
# EVALUATION / SCORE FUNCTIONS
# ============================================================

def get_score_ledger(enrollment_id: str) -> list:
    return _serialize(list(get_collection("enrollmentscoreledgers").find(
        {"enrollmentId": ObjectId(enrollment_id)}
    ).sort("recordedAt", -1)))


def record_score(enrollment_id: str, component_type: str, marks: float, max_marks: float,
                 assessment_component_id: str = None, assessment_component_title: str = None) -> dict:
    record = {
        "enrollmentId": ObjectId(enrollment_id),
        "componentType": component_type,
        "marksAwarded": marks,
        "maxMarks": max_marks,
        "recordedAt": datetime.utcnow()
    }
    if assessment_component_id:
        record["assessmentComponentId"] = ObjectId(assessment_component_id)
    if assessment_component_title:
        record["assessmentComponentTitle"] = assessment_component_title

    result = get_collection("enrollmentscoreledgers").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


def get_mentor_eval_scores(enrollment_id: str = None, mentor_id: str = None) -> list:
    query = {}
    if enrollment_id:
        query["enrollmentId"] = ObjectId(enrollment_id)
    if mentor_id:
        query["mentorId"] = ObjectId(mentor_id)
    return _serialize(list(get_collection("mentorevaluationscores").find(query).sort("submittedAt", -1)))


def submit_mentor_evaluation(enrollment_id: str, mentor_id: str, fields: list,
                             overall_comment: str = None) -> dict:
    enrollment = get_collection("studenttrackenrollments").find_one({"_id": ObjectId(enrollment_id)})
    if not enrollment:
        return {"error": "Enrollment not found"}

    total_marks = sum(f.get("marksAwarded", 0) for f in fields)
    total_max = sum(f.get("maxMarks", 0) for f in fields)

    record = {
        "sessionId": enrollment["sessionId"],
        "enrollmentId": ObjectId(enrollment_id),
        "studentId": enrollment["studentId"],
        "trackSessionConfigId": enrollment["trackSessionConfigId"],
        "mentorId": ObjectId(mentor_id),
        "fields": fields,
        "overallComment": overall_comment,
        "totalMarksAwarded": total_marks,
        "totalMaxMarks": total_max,
        "submittedAt": datetime.utcnow()
    }

    result = get_collection("mentorevaluationscores").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


def get_marks_hierarchy() -> list:
    pipeline = [
        {"$lookup": {"from": "tracksessionconfigs", "localField": "trackSessionConfigId", "foreignField": "_id", "as": "config"}},
        {"$unwind": "$config"},
        {"$lookup": {"from": "tracks", "localField": "config.trackId", "foreignField": "_id", "as": "track"}},
        {"$unwind": "$track"},
        {"$group": {
            "_id": {"trackName": "$track.name", "trackCode": "$track.code"},
            "enrollmentCount": {"$sum": 1},
            "avgMarks": {"$avg": "$marksAwarded"}
        }},
        {"$sort": {"_id.trackName": 1}}
    ]
    return _serialize(list(get_collection("enrollmentscoreledgers").aggregate(pipeline)))


# ============================================================
# MENTOR FUNCTIONS
# ============================================================

def get_mentor_assignments(mentor_id: str, session_id: str = None) -> list:
    query = {"mentorId": ObjectId(mentor_id), "isActive": True}
    if session_id:
        query["sessionId"] = ObjectId(session_id)
    return _serialize(list(get_collection("enrollmentmentorassignments").find(query).sort("assignedAt", -1)))


def get_student_mentor(student_id: str = None) -> dict:
    if not student_id:
        return {"error": "student_id is required"}

    # Primary: check enrollmentmentorassignments
    assignment = get_collection("enrollmentmentorassignments").find_one(
        {"studentId": ObjectId(student_id), "isActive": True},
        sort=[("assignedAt", -1)]
    )
    if assignment:
        mentor = get_collection("users").find_one({"_id": assignment["mentorId"]})
        return _serialize({
            "assigned": True,
            "source": "enrollmentmentorassignments",
            "assignment": assignment,
            "mentor": {
                "id": str(mentor["_id"]),
                "name": mentor.get("name"),
                "email": mentor.get("email"),
                "mobileNumber": mentor.get("mobileNumber")
            } if mentor else None
        })

    # Fallback: check studenttrackenrollments.mentorId field
    enrollment = get_collection("studenttrackenrollments").find_one(
        {"studentId": ObjectId(student_id), "mentorId": {"$ne": None}},
        sort=[("startedAt", -1)]
    )
    if enrollment and enrollment.get("mentorId"):
        mentor = get_collection("users").find_one({"_id": enrollment["mentorId"]})
        return _serialize({
            "assigned": True,
            "source": "studenttrackenrollments",
            "enrollment": enrollment,
            "mentor": {
                "id": str(mentor["_id"]),
                "name": mentor.get("name"),
                "email": mentor.get("email"),
                "mobileNumber": mentor.get("mobileNumber")
            } if mentor else None
        })

    return {"assigned": False, "message": "No active mentor assignment found"}


def assign_student_to_mentor(enrollment_id: str, mentor_id: str) -> dict:
    enrollment = get_collection("studenttrackenrollments").find_one({"_id": ObjectId(enrollment_id)})
    if not enrollment:
        return {"error": "Enrollment not found"}

    existing = get_collection("enrollmentmentorassignments").find_one({
        "enrollmentId": ObjectId(enrollment_id),
        "isActive": True
    })
    if existing:
        return {"error": "Student already has an active mentor assignment"}

    record = {
        "sessionId": enrollment["sessionId"],
        "enrollmentId": ObjectId(enrollment_id),
        "studentId": enrollment["studentId"],
        "mentorId": ObjectId(mentor_id),
        "assignedAt": datetime.utcnow(),
        "isActive": True
    }
    result = get_collection("enrollmentmentorassignments").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


def release_mentor_assignment(assignment_id: str, reason: str = None) -> dict:
    update = {"isActive": False, "releasedAt": datetime.utcnow()}
    if reason:
        update["releaseReason"] = reason
    get_collection("enrollmentmentorassignments").update_one(
        {"_id": ObjectId(assignment_id)}, {"$set": update}
    )
    return _serialize(get_collection("enrollmentmentorassignments").find_one({"_id": ObjectId(assignment_id)}))


def list_interactions(enrollment_id: str = None, mentor_id: str = None,
                      status: str = None, page: int = 1, page_size: int = 20) -> dict:
    query = {}
    if enrollment_id:
        query["enrollmentId"] = ObjectId(enrollment_id)
    if mentor_id:
        query["mentorId"] = ObjectId(mentor_id)
    if status:
        query["status"] = status
    total = get_collection("mentorstudentinteractions").count_documents(query)
    skip = (page - 1) * page_size
    items = list(get_collection("mentorstudentinteractions").find(query).skip(skip).limit(page_size).sort("createdAt", -1))
    return {"items": _serialize(items), "total": total, "page": page, "pageSize": page_size}


def get_interaction(interaction_id: str) -> dict:
    return _serialize(get_collection("mentorstudentinteractions").find_one({"_id": ObjectId(interaction_id)}))


def create_interaction(enrollment_id: str, mentor_id: str, title: str, interaction_number: int) -> dict:
    enrollment = get_collection("studenttrackenrollments").find_one({"_id": ObjectId(enrollment_id)})
    if not enrollment:
        return {"error": "Enrollment not found"}

    record = {
        "sessionId": enrollment["sessionId"],
        "enrollmentId": ObjectId(enrollment_id),
        "assignmentId": None,
        "trackSessionConfigId": enrollment["trackSessionConfigId"],
        "studentId": enrollment["studentId"],
        "mentorId": ObjectId(mentor_id),
        "interactionNumber": interaction_number,
        "title": title,
        "status": "PENDING",
        "createdAt": datetime.utcnow()
    }
    result = get_collection("mentorstudentinteractions").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


def update_interaction(interaction_id: str, fields: dict) -> dict:
    allowed = {"title", "summary", "notes", "nextAction", "meetingLink", "meetingMode", "status"}
    update = {k: v for k, v in fields.items() if k in allowed}
    if update:
        get_collection("mentorstudentinteractions").update_one(
            {"_id": ObjectId(interaction_id)}, {"$set": update}
        )
    return get_interaction(interaction_id)


def finalize_interaction(interaction_id: str, score_awarded: float, max_score: float,
                         summary: str = None) -> dict:
    update = {
        "status": "COMPLETED",
        "scoreAwarded": score_awarded,
        "maxScore": max_score,
        "endedAt": datetime.utcnow(),
        "finalizedAt": datetime.utcnow()
    }
    if summary:
        update["summary"] = summary
    get_collection("mentorstudentinteractions").update_one(
        {"_id": ObjectId(interaction_id)}, {"$set": update}
    )
    return get_interaction(interaction_id)


def get_student_progress(assignment_id: str) -> dict:
    return _serialize(get_collection("studentprogresses").find_one({"assignmentId": ObjectId(assignment_id)}))


# ============================================================
# ANNOUNCEMENT FUNCTIONS
# ============================================================

def list_announcements(user_id: str = None, user_role: str = None, page: int = 1, page_size: int = 20) -> dict:
    try:
        # Ensure page/page_size are valid integers
        page = max(1, int(page)) if page else 1
        page_size = min(max(1, int(page_size)) if page_size else 20, 100)

        query = {"isDeleted": {"$ne": True}}

        if user_id and user_role:
            role_upper = str(user_role).upper()
            # Filter by audience
            query["$or"] = [
                {"audience": "BOTH"},
                {"audience": role_upper}
            ]
            # For students, also filter by trackScope
            if role_upper == "STUDENT":
                # Get student's track names from enrollments
                enrollments = list(get_collection("studenttrackenrollments").find(
                    {"studentId": ObjectId(user_id), "status": {"$in": ["ACTIVE", "ENROLLED"]}},
                    {"trackSessionConfigId": 1}
                ))
                track_config_ids = [e["trackSessionConfigId"] for e in enrollments if "trackSessionConfigId" in e]

                # Get track names from configs
                track_names = []
                if track_config_ids:
                    configs = list(get_collection("tracksessionconfigs").find(
                        {"_id": {"$in": track_config_ids}},
                        {"trackId": 1}
                    ))
                    track_ids = [c["trackId"] for c in configs if "trackId" in c]
                    if track_ids:
                        tracks = list(get_collection("tracks").find(
                            {"_id": {"$in": track_ids}},
                            {"name": 1}
                        ))
                        track_names = [t["name"] for t in tracks if "name" in t]

                # Add trackScope filter
                if track_names:
                    query["$and"] = [
                        {"$or": [
                            {"trackScope": "ALL_TRACKS"},
                            {"trackScope": "SELECTED_TRACKS", "targetTrackNames": {"$in": track_names}},
                            {"trackScope": {"$exists": False}}
                        ]}
                    ]
                else:
                    # No enrollments — only show ALL_TRACKS or unspecified
                    query["$and"] = [
                        {"$or": [
                            {"trackScope": "ALL_TRACKS"},
                            {"trackScope": {"$exists": False}}
                        ]}
                    ]

        total = get_collection("announcements").count_documents(query)
        skip = (page - 1) * page_size
        items = list(get_collection("announcements").find(query).skip(skip).limit(page_size).sort("createdAt", -1))
        return {"items": _serialize(items), "total": total, "page": page, "pageSize": page_size}
    except Exception as e:
        # Fallback: return all non-deleted announcements without filtering
        try:
            fallback_query = {"isDeleted": {"$ne": True}}
            total = get_collection("announcements").count_documents(fallback_query)
            items = list(get_collection("announcements").find(fallback_query).limit(20).sort("createdAt", -1))
            return {"items": _serialize(items), "total": total, "page": 1, "pageSize": 20, "warning": f"Filtered query failed: {str(e)}"}
        except Exception:
            return {"items": [], "total": 0, "page": 1, "pageSize": 20, "error": str(e)}


def get_announcement(announcement_id: str) -> dict:
    return _serialize(get_collection("announcements").find_one({"_id": ObjectId(announcement_id)}))


def create_announcement(title: str, message: str, audience: str, creator_user_id: str,
                        track_scope: str = "ALL_TRACKS") -> dict:
    creator = get_collection("users").find_one({"_id": ObjectId(creator_user_id)})
    if not creator:
        return {"error": "Creator not found"}

    record = {
        "title": title,
        "message": message,
        "audience": audience,
        "trackScope": track_scope,
        "deliveryChannels": ["IN_APP"],
        "creatorUserId": ObjectId(creator_user_id),
        "creatorRole": "ADMIN" if "ADMIN" in creator.get("roles", []) else "MENTOR",
        "creatorName": creator.get("name", ""),
        "creatorEmail": creator.get("email", ""),
        "recipientCount": 0,
        "readCount": 0,
        "createdAt": datetime.utcnow()
    }
    result = get_collection("announcements").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


# ============================================================
# NOTIFICATION FUNCTIONS
# ============================================================

def list_notifications(user_id: str, status: str = None, page: int = 1, page_size: int = 20) -> dict:
    query = {"userId": ObjectId(user_id)}
    if status:
        query["status"] = status
    total = get_collection("notifications").count_documents(query)
    skip = (page - 1) * page_size
    items = list(get_collection("notifications").find(query).skip(skip).limit(page_size).sort("createdAt", -1))
    return {"items": _serialize(items), "total": total, "page": page, "pageSize": page_size}


def get_unread_count(user_id: str) -> int:
    return get_collection("notifications").count_documents({
        "userId": ObjectId(user_id),
        "readAt": None
    })


def mark_notification_read(notification_id: str) -> dict:
    get_collection("notifications").update_one(
        {"_id": ObjectId(notification_id)},
        {"$set": {"readAt": datetime.utcnow()}}
    )
    return _serialize(get_collection("notifications").find_one({"_id": ObjectId(notification_id)}))


def create_notification(user_id: str, title: str, message: str, notif_type: str,
                        action_url: str = None) -> dict:
    record = {
        "userId": ObjectId(user_id),
        "type": notif_type,
        "title": title,
        "message": message,
        "actionUrl": action_url,
        "eventKey": f"{notif_type}_{datetime.utcnow().timestamp()}",
        "status": "SENT",
        "createdAt": datetime.utcnow()
    }
    result = get_collection("notifications").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


# ============================================================
# TEAM FUNCTIONS
# ============================================================

def list_teams(session_id: str = None, track_config_id: str = None) -> list:
    query = {}
    if session_id:
        query["sessionId"] = ObjectId(session_id)
    if track_config_id:
        query["trackSessionConfigId"] = ObjectId(track_config_id)
    return _serialize(list(get_collection("teams").find(query)))


def get_team(team_id: str) -> dict:
    cache_key = f"team:{team_id}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached
    result = _serialize(get_collection("teams").find_one({"_id": ObjectId(team_id)}))
    if result:
        _set_cache(cache_key, result)
    return result


def create_team(name: str, leader_id: str, session_id: str, track_session_config_id: str) -> dict:
    import secrets
    record = {
        "name": name,
        "inviteCode": secrets.token_hex(4).upper(),
        "sessionId": ObjectId(session_id),
        "trackSessionConfigId": ObjectId(track_session_config_id),
        "leaderId": ObjectId(leader_id),
        "memberIds": [ObjectId(leader_id)],
        "source": "STUDENT_CREATED",
        "status": "FORMING",
        "createdAt": datetime.utcnow()
    }
    result = get_collection("teams").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


def join_team(invite_code: str, student_id: str) -> dict:
    team = get_collection("teams").find_one({"inviteCode": invite_code.upper()})
    if not team:
        return {"error": "Invalid invite code"}
    if team["status"] != "FORMING":
        return {"error": "Team is no longer accepting members"}

    student_oid = ObjectId(student_id)
    if student_oid in team.get("memberIds", []):
        return {"error": "Already a member of this team"}

    get_collection("teams").update_one(
        {"_id": team["_id"]},
        {"$addToSet": {"memberIds": student_oid}}
    )
    return get_team(str(team["_id"]))


def invite_to_team(team_id: str, inviter_id: str, invitee_id: str) -> dict:
    record = {
        "teamId": ObjectId(team_id),
        "inviterId": ObjectId(inviter_id),
        "inviteeId": ObjectId(invitee_id),
        "status": "PENDING",
        "createdAt": datetime.utcnow()
    }
    result = get_collection("teaminvitations").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


def respond_to_invitation(invitation_id: str, response: str) -> dict:
    if response not in ("ACCEPTED", "DECLINED"):
        return {"error": "Response must be ACCEPTED or DECLINED"}

    update = {"status": response, "respondedAt": datetime.utcnow()}
    get_collection("teaminvitations").update_one(
        {"_id": ObjectId(invitation_id)}, {"$set": update}
    )

    if response == "ACCEPTED":
        invitation = get_collection("teaminvitations").find_one({"_id": ObjectId(invitation_id)})
        if invitation:
            get_collection("teams").update_one(
                {"_id": invitation["teamId"]},
                {"$addToSet": {"memberIds": invitation["inviteeId"]}}
            )

    return _serialize(get_collection("teaminvitations").find_one({"_id": ObjectId(invitation_id)}))


# ============================================================
# ONBOARDING FUNCTIONS
# ============================================================

def get_onboarding_status(enrollment_id: str) -> dict:
    enrollment = get_collection("studenttrackenrollments").find_one({"_id": ObjectId(enrollment_id)})
    if not enrollment:
        return {"error": "Enrollment not found"}

    submissions = list(get_collection("trackonboardingsubmissions").find({"enrollmentId": ObjectId(enrollment_id)}))
    return _serialize({
        "enrollment": enrollment,
        "isOnboardingSubmitted": enrollment.get("isOnboardingSubmitted", False),
        "submissionCount": len(submissions),
        "submissions": submissions
    })


def get_submissions(enrollment_id: str = None, status: str = None, kind: str = None) -> list:
    query = {}
    if enrollment_id:
        query["enrollmentId"] = ObjectId(enrollment_id)
    if status:
        query["status"] = status
    if kind:
        query["submissionKind"] = kind
    return _serialize(list(get_collection("trackonboardingsubmissions").find(query).sort("submittedAt", -1)))


def submit_intake_form(enrollment_id: str, template_id: str, responses: dict) -> dict:
    enrollment = get_collection("studenttrackenrollments").find_one({"_id": ObjectId(enrollment_id)})
    if not enrollment:
        return {"error": "Enrollment not found"}

    record = {
        "submissionKind": "INTAKE",
        "studentId": enrollment["studentId"],
        "sessionId": enrollment["sessionId"],
        "enrollmentId": ObjectId(enrollment_id),
        "trackSessionConfigId": enrollment["trackSessionConfigId"],
        "intakeTemplateId": ObjectId(template_id),
        "attemptNumber": 1,
        "responseData": responses,
        "status": "SUBMITTED",
        "submittedAt": datetime.utcnow()
    }
    result = get_collection("trackonboardingsubmissions").insert_one(record)
    record["_id"] = str(result.inserted_id)
    return _serialize(record)


# ============================================================
# ACADEMIC YEAR FUNCTIONS
# ============================================================

def get_current_session() -> dict:
    return _serialize(get_collection("academicyears").find_one({"isActive": True}))


def list_academic_years(page: int = 1, page_size: int = 20) -> dict:
    total = get_collection("academicyears").count_documents({})
    skip = (page - 1) * page_size
    items = list(get_collection("academicyears").find({}).skip(skip).limit(page_size).sort("sessionYear", -1))
    return {"items": _serialize(items), "total": total, "page": page, "pageSize": page_size}


# ============================================================
# FUNCTION REGISTRY
# ============================================================

FUNCTIONS = {
    "get_user_by_id": {
        "description": "Fetch a user by their ID",
        "params": {"user_id": "string"},
        "handler": get_user_by_id,
        "permission": "read",
        "collection": "users"
    },
    "get_user_by_email": {
        "description": "Fetch a user by email address",
        "params": {"email": "string"},
        "handler": get_user_by_email,
        "permission": "read",
        "collection": "users"
    },
    "list_users": {
        "description": "List users with optional filters (role, search)",
        "params": {"role": "string (optional)", "search": "string (optional)", "page": "int (default 1)", "page_size": "int (default 20)"},
        "handler": list_users,
        "permission": "read",
        "collection": "users"
    },
    "update_user": {
        "description": "Update user fields",
        "params": {"user_id": "string", "fields": "dict"},
        "handler": update_user,
        "permission": "write",
        "collection": "users"
    },
    "list_tracks": {
        "description": "List all tracks with optional search",
        "params": {"search": "string (optional)"},
        "handler": list_tracks,
        "permission": "read",
        "collection": "tracks"
    },
    "get_track": {
        "description": "Get a track by ID",
        "params": {"track_id": "string"},
        "handler": get_track,
        "permission": "read",
        "collection": "tracks"
    },
    "get_track_by_code": {
        "description": "Get a track by its code (e.g., WEB, AI)",
        "params": {"code": "string"},
        "handler": get_track_by_code,
        "permission": "read",
        "collection": "tracks"
    },
    "list_track_configs": {
        "description": "List track session configs for a session",
        "params": {"session_id": "string (optional)", "search": "string (optional)"},
        "handler": list_track_configs,
        "permission": "read",
        "collection": "tracksessionconfigs"
    },
    "get_track_config": {
        "description": "Get a track config by session and track",
        "params": {"session_id": "string", "track_id": "string"},
        "handler": get_track_config,
        "permission": "read",
        "collection": "tracksessionconfigs"
    },
    "get_track_config_by_id": {
        "description": "Get a track config by its ID",
        "params": {"config_id": "string"},
        "handler": get_track_config_by_id,
        "permission": "read",
        "collection": "tracksessionconfigs"
    },
    "list_enrollments": {
        "description": "List enrollments with filters (student, track config, status)",
        "params": {"student_id": "string (optional)", "track_config_id": "string (optional)", "status": "string (optional)", "page": "int", "page_size": "int"},
        "handler": list_enrollments,
        "permission": "read",
        "collection": "studenttrackenrollments"
    },
    "get_enrollment": {
        "description": "Get an enrollment by ID",
        "params": {"enrollment_id": "string"},
        "handler": get_enrollment,
        "permission": "read",
        "collection": "studenttrackenrollments"
    },
    "get_student_enrollments": {
        "description": "Get all enrollments for a student",
        "params": {"student_id": "string", "session_id": "string (optional)"},
        "handler": get_student_enrollments,
        "permission": "read",
        "collection": "studenttrackenrollments"
    },
    "update_enrollment_status": {
        "description": "Change enrollment status (ACTIVE, INACTIVE, COMPLETED, etc.)",
        "params": {"enrollment_id": "string", "status": "string", "reason": "string (optional)"},
        "handler": update_enrollment_status,
        "permission": "write",
        "collection": "studenttrackenrollments"
    },
    "mark_attendance": {
        "description": "Mark attendance for a student (PRESENT or ABSENT)",
        "params": {"enrollment_id": "string", "date_key": "string (YYYY-MM-DD)", "status": "string (PRESENT/ABSENT)", "session": "string (MORNING/EVENING)"},
        "handler": mark_attendance,
        "permission": "write",
        "collection": "studentattendances"
    },
    "get_student_attendance": {
        "description": "Get attendance records for a student",
        "params": {"student_id": "string", "session_id": "string (optional)", "start_date": "string (optional)", "end_date": "string (optional)"},
        "handler": get_student_attendance,
        "permission": "read",
        "collection": "studentattendances"
    },
    "get_session_attendance": {
        "description": "Get all attendance for a track config on a specific date",
        "params": {"track_config_id": "string", "date_key": "string", "session": "string (optional)"},
        "handler": get_session_attendance,
        "permission": "read",
        "collection": "studentattendances"
    },
    "get_attendance_stats": {
        "description": "Get attendance statistics (percentage, present/absent counts)",
        "params": {"enrollment_id": "string (optional)", "student_id": "string (optional)"},
        "handler": get_attendance_stats,
        "permission": "read",
        "collection": "studentattendances"
    },
    "get_score_ledger": {
        "description": "Get score records for an enrollment",
        "params": {"enrollment_id": "string"},
        "handler": get_score_ledger,
        "permission": "read",
        "collection": "enrollmentscoreledgers"
    },
    "record_score": {
        "description": "Record a score for an enrollment",
        "params": {"enrollment_id": "string", "component_type": "string", "marks": "float", "max_marks": "float"},
        "handler": record_score,
        "permission": "write",
        "collection": "enrollmentscoreledgers"
    },
    "get_mentor_eval_scores": {
        "description": "Get mentor evaluation scores",
        "params": {"enrollment_id": "string (optional)", "mentor_id": "string (optional)"},
        "handler": get_mentor_eval_scores,
        "permission": "read",
        "collection": "mentorevaluationscores"
    },
    "submit_mentor_evaluation": {
        "description": "Submit mentor evaluation with field-level scores",
        "params": {"enrollment_id": "string", "mentor_id": "string", "fields": "list[dict]", "overall_comment": "string (optional)"},
        "handler": submit_mentor_evaluation,
        "permission": "write",
        "collection": "mentorevaluationscores"
    },
    "get_marks_hierarchy": {
        "description": "Get marks hierarchy grouped by track",
        "params": {},
        "handler": get_marks_hierarchy,
        "permission": "read",
        "collection": "enrollmentscoreledgers"
    },
    "get_mentor_assignments": {
        "description": "Get students assigned to a mentor",
        "params": {"mentor_id": "string", "session_id": "string (optional)"},
        "handler": get_mentor_assignments,
        "permission": "read",
        "collection": "enrollmentmentorassignments"
    },
    "get_student_mentor": {
        "description": "Get the active mentor for a student. Students use this to check who their mentor is.",
        "params": {"student_id": "string (optional, defaults to logged-in user)"},
        "handler": get_student_mentor,
        "permission": "read",
        "collection": "enrollmentmentorassignments"
    },
    "assign_student_to_mentor": {
        "description": "Assign a student to a mentor",
        "params": {"enrollment_id": "string", "mentor_id": "string"},
        "handler": assign_student_to_mentor,
        "permission": "write",
        "collection": "enrollmentmentorassignments"
    },
    "release_mentor_assignment": {
        "description": "Release a mentor-student assignment",
        "params": {"assignment_id": "string", "reason": "string (optional)"},
        "handler": release_mentor_assignment,
        "permission": "write",
        "collection": "enrollmentmentorassignments"
    },
    "list_interactions": {
        "description": "List mentor-student interactions",
        "params": {"enrollment_id": "string (optional)", "mentor_id": "string (optional)", "status": "string (optional)", "page": "int", "page_size": "int"},
        "handler": list_interactions,
        "permission": "read",
        "collection": "mentorstudentinteractions"
    },
    "get_interaction": {
        "description": "Get an interaction by ID",
        "params": {"interaction_id": "string"},
        "handler": get_interaction,
        "permission": "read",
        "collection": "mentorstudentinteractions"
    },
    "create_interaction": {
        "description": "Create a new mentor-student interaction",
        "params": {"enrollment_id": "string", "mentor_id": "string", "title": "string", "interaction_number": "int"},
        "handler": create_interaction,
        "permission": "write",
        "collection": "mentorstudentinteractions"
    },
    "update_interaction": {
        "description": "Update interaction fields (title, summary, notes, status)",
        "params": {"interaction_id": "string", "fields": "dict"},
        "handler": update_interaction,
        "permission": "write",
        "collection": "mentorstudentinteractions"
    },
    "finalize_interaction": {
        "description": "Finalize an interaction with score",
        "params": {"interaction_id": "string", "score_awarded": "float", "max_score": "float", "summary": "string (optional)"},
        "handler": finalize_interaction,
        "permission": "write",
        "collection": "mentorstudentinteractions"
    },
    "get_student_progress": {
        "description": "Get student progress tracker",
        "params": {"assignment_id": "string"},
        "handler": get_student_progress,
        "permission": "read",
        "collection": "studentprogresses"
    },
    "list_announcements": {
        "description": "List announcements for the user's role",
        "params": {"user_id": "string (optional)", "user_role": "string (optional)", "page": "int", "page_size": "int"},
        "handler": list_announcements,
        "permission": "read",
        "collection": "announcements"
    },
    "get_announcement": {
        "description": "Get an announcement by ID",
        "params": {"announcement_id": "string"},
        "handler": get_announcement,
        "permission": "read",
        "collection": "announcements"
    },
    "create_announcement": {
        "description": "Create a new announcement",
        "params": {"title": "string", "message": "string", "audience": "string (STUDENTS/MENTORS/BOTH)", "creator_user_id": "string"},
        "handler": create_announcement,
        "permission": "write",
        "collection": "announcements"
    },
    "list_notifications": {
        "description": "List notifications for a user",
        "params": {"user_id": "string", "status": "string (optional)", "page": "int", "page_size": "int"},
        "handler": list_notifications,
        "permission": "read",
        "collection": "notifications"
    },
    "get_unread_count": {
        "description": "Get count of unread notifications",
        "params": {"user_id": "string"},
        "handler": get_unread_count,
        "permission": "read",
        "collection": "notifications"
    },
    "mark_notification_read": {
        "description": "Mark a notification as read",
        "params": {"notification_id": "string"},
        "handler": mark_notification_read,
        "permission": "write",
        "collection": "notifications"
    },
    "create_notification": {
        "description": "Create a notification for a user",
        "params": {"user_id": "string", "title": "string", "message": "string", "notif_type": "string"},
        "handler": create_notification,
        "permission": "write",
        "collection": "notifications"
    },
    "list_teams": {
        "description": "List teams for a session, optionally filtered by track config",
        "params": {"session_id": "string (optional)", "track_config_id": "string (optional)"},
        "handler": list_teams,
        "permission": "read",
        "collection": "teams"
    },
    "get_team": {
        "description": "Get a team by ID",
        "params": {"team_id": "string"},
        "handler": get_team,
        "permission": "read",
        "collection": "teams"
    },
    "create_team": {
        "description": "Create a new team",
        "params": {"name": "string", "leader_id": "string", "session_id": "string", "track_session_config_id": "string"},
        "handler": create_team,
        "permission": "write",
        "collection": "teams"
    },
    "join_team": {
        "description": "Join a team using invite code",
        "params": {"invite_code": "string", "student_id": "string"},
        "handler": join_team,
        "permission": "write",
        "collection": "teams"
    },
    "invite_to_team": {
        "description": "Send team invitation to a student",
        "params": {"team_id": "string", "inviter_id": "string", "invitee_id": "string"},
        "handler": invite_to_team,
        "permission": "write",
        "collection": "teaminvitations"
    },
    "respond_to_invitation": {
        "description": "Accept or decline a team invitation",
        "params": {"invitation_id": "string", "response": "string (ACCEPTED/DECLINED)"},
        "handler": respond_to_invitation,
        "permission": "write",
        "collection": "teaminvitations"
    },
    "get_onboarding_status": {
        "description": "Get onboarding status for an enrollment",
        "params": {"enrollment_id": "string"},
        "handler": get_onboarding_status,
        "permission": "read",
        "collection": "trackonboardingsubmissions"
    },
    "get_submissions": {
        "description": "List document/intake submissions",
        "params": {"enrollment_id": "string (optional)", "status": "string (optional)", "kind": "string (optional)"},
        "handler": get_submissions,
        "permission": "read",
        "collection": "trackonboardingsubmissions"
    },
    "submit_intake_form": {
        "description": "Submit intake form responses",
        "params": {"enrollment_id": "string", "template_id": "string", "responses": "dict"},
        "handler": submit_intake_form,
        "permission": "write",
        "collection": "trackonboardingsubmissions"
    },
    "get_current_session": {
        "description": "Get the current active academic session",
        "params": {},
        "handler": get_current_session,
        "permission": "read",
        "collection": "academicyears"
    },
    "list_academic_years": {
        "description": "List academic years",
        "params": {"page": "int", "page_size": "int"},
        "handler": list_academic_years,
        "permission": "read",
        "collection": "academicyears"
    }
}


def execute_function(name: str, params: dict, user_role: str) -> dict:
    func = FUNCTIONS.get(name)
    if not func:
        return {"error": f"Unknown function: {name}"}

    # Check permission
    from agent.permissions import can_read, can_write
    collection = func.get("collection", "")
    if func["permission"] == "write" and not can_write(user_role, collection):
        return {"error": f"Permission denied: {user_role} cannot write to {collection}"}
    if func["permission"] == "read" and not can_read(user_role, collection):
        return {"error": f"Permission denied: {user_role} cannot read {collection}"}

    try:
        handler = func["handler"]
        result = handler(**params)
        return result
    except Exception as e:
        return {"error": str(e)}
