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
# USER CONTEXT (for system prompt enrichment)
# ============================================================

def get_user_context(user_id: str, role: str = None) -> str:
    """Build role-specific context string with pre-fetched user data."""
    if not role:
        user = get_collection("users").find_one({"_id": ObjectId(user_id)})
        role = (user.get("roles") or ["STUDENT"])[0] if user else "STUDENT"
    
    cache_key = f"context:{user_id}:{role}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached
    
    if role == "STUDENT":
        result = _build_student_context(user_id)
    elif role == "MENTOR":
        result = _build_mentor_context(user_id)
    elif role == "ADMIN":
        result = _build_admin_context(user_id)
    else:
        result = ""
    
    _set_cache(cache_key, result)
    return result


def _build_student_context(user_id: str) -> str:
    """Build comprehensive context for student role."""
    lines = ["## Your Info"]
    
    # User info
    user = get_collection("users").find_one({"_id": ObjectId(user_id)})
    if user:
        lines.append(f"- User ID: {user_id}")
        lines.append(f"- Name: {user.get('name', 'Unknown')}")
        lines.append(f"- Email: {user.get('email', 'N/A')}")
        lines.append(f"- Roll Number: {user.get('rollNumber', 'N/A')}")
        lines.append(f"- Programme: {user.get('programme', 'N/A')}")
        lines.append(f"- Section: {user.get('section', 'N/A')}")
        lines.append(f"- Year: {user.get('studentYear', 'N/A')}")
    
    # Active enrollment
    enrollment = get_collection("studenttrackenrollments").find_one(
        {"studentId": ObjectId(user_id), "status": {"$in": ["ACTIVE", "ENROLLED", "PENDING_ONBOARDING"]}},
        sort=[("startedAt", -1)]
    )
    
    if enrollment:
        lines.append("\n## Your Enrollment")
        lines.append(f"- Status: {enrollment.get('status')}")
        
        session = get_collection("academicyears").find_one({"_id": enrollment["sessionId"]})
        track = get_collection("tracksessionconfigs").find_one({"_id": enrollment["trackSessionConfigId"]})
        
        if session:
            lines.append(f"- Session: {session.get('name', str(enrollment['sessionId']))} (ID: {str(enrollment['sessionId'])})")
        if track:
            lines.append(f"- Track: {track.get('name', str(enrollment['trackSessionConfigId']))} (ID: {str(enrollment['trackSessionConfigId'])})")
            lines.append(f"- Track Mode: {track.get('mode', 'UNKNOWN')}")
        lines.append(f"- Enrollment ID: {str(enrollment['_id'])}")
        lines.append(f"- Onboarding: {'Completed' if enrollment.get('isOnboardingSubmitted') else 'Pending'}")
        
        # Team membership
        team = get_collection("teams").find_one({"memberIds": ObjectId(user_id)})
        if team:
            lines.append("\n## Your Team")
            lines.append(f"- Team: {team.get('name', 'Unnamed')} (ID: {str(team['_id'])})")
            leader_id = team.get("leaderId")
            lines.append(f"- Role: {'Leader' if str(leader_id) == user_id else 'Member'}")
            member_ids = team.get("memberIds", [])
            if len(member_ids) > 1:
                member_docs = list(get_collection("users").find({"_id": {"$in": member_ids}}))
                lines.append("- Members:")
                for m in member_docs:
                    role_label = "Leader" if str(m["_id"]) == str(leader_id) else "Member"
                    lines.append(f"  - {m.get('name', 'Unknown')} (ID: {str(m['_id'])}) — {role_label}")
        
        # Mentor
        assignment = get_collection("enrollmentmentorassignments").find_one(
            {"studentId": ObjectId(user_id), "isActive": True},
            sort=[("assignedAt", -1)]
        )
        if assignment:
            mentor = get_collection("users").find_one({"_id": assignment["mentorId"]})
            if mentor:
                lines.append("\n## Your Mentor")
                lines.append(f"- {mentor.get('name', 'Unknown')} (ID: {str(mentor['_id'])})")
                lines.append(f"- Email: {mentor.get('email', 'N/A')}")
                lines.append(f"- Phone: {mentor.get('mobileNumber', 'N/A')}")
        
        # Track criteria
        if track:
            components = track.get("assessmentComponents", [])
            active_components = [c for c in components if c.get("isActive")]
            if active_components:
                lines.append(f"\n## Your Track Criteria ({track.get('name', 'Track')})")
                ledger = list(get_collection("enrollmentscoreledgers").find({"enrollmentId": enrollment["_id"]}))
                # Only count ledger entries that match active component IDs
                active_comp_ids = {str(c["_id"]) for c in active_components}
                matched_ledger = [l for l in ledger if str(l.get("assessmentComponentId", "")) in active_comp_ids]
                for comp in active_components:
                    comp_type = comp.get("type")
                    comp_title = comp.get("title", comp_type)
                    max_marks = comp.get("maxMarks", 0)
                    # Sum marks from ledger for this component
                    comp_marks = sum(l.get("marksAwarded", 0) for l in matched_ledger if str(l.get("assessmentComponentId", "")) == str(comp["_id"]))
                    percentage = round(comp_marks / max_marks * 100, 1) if max_marks > 0 else 0
                    lines.append(f"- {comp_title}: {comp_marks}/{max_marks} ({percentage}%)")
                
                # Total
                total_awarded = sum(l.get("marksAwarded", 0) for l in matched_ledger)
                total_max = sum(c.get("maxMarks", 0) for c in active_components)
                total_pct = round(total_awarded / total_max * 100, 1) if total_max > 0 else 0
                lines.append(f"- **Total: {total_awarded}/{total_max} ({total_pct}%)**")
        
        # Documents - show templates and their submission status
        # Get existing submissions for this enrollment
        submissions = list(get_collection("trackonboardingsubmissions").find({
            "enrollmentId": enrollment["_id"],
        }))
        
        # Find templates from the track config that has them
        # (enrollment's trackSessionConfigId may have 0 templates; check parent tracks too)
        templates = []
        if track:
            templates = [t for t in (track.get("documentTemplates") or []) if t.get("isActive", True)]
        
        # If no templates in enrollment's track config, look at submission template IDs
        # and find which track config has those templates
        if not templates and submissions:
            # Get unique template IDs from submissions
            submitted_tpl_ids = set()
            for sub in submissions:
                tpl_id = sub.get("documentTemplateId")
                if tpl_id:
                    submitted_tpl_ids.add(str(tpl_id))
            
            # Search all tracksessionconfigs for matching templates
            all_tcs = get_collection("tracksessionconfigs").find({
                "sessionId": enrollment["sessionId"],
            })
            for tc in all_tcs:
                for tmpl in (tc.get("documentTemplates") or []):
                    if str(tmpl.get("_id")) in submitted_tpl_ids:
                        templates.append(tmpl)
                        # Also use this track's templates as the full list
                if templates:
                    # Found the right track config — use ALL its templates
                    templates = [t for t in (tc.get("documentTemplates") or []) if t.get("isActive", True)]
                    break
        
        if templates:
            lines.append("\n## Your Required Documents")
            # Map template ID to latest submission status
            submission_map = {}
            for sub in submissions:
                tpl_id = str(sub.get("documentTemplateId", ""))
                if tpl_id:
                    sub_status = sub.get("status", "UNKNOWN")
                    # Keep latest submission per template
                    if tpl_id not in submission_map or (sub.get("submittedAt") or "") > (submission_map[tpl_id].get("submittedAt") or ""):
                        submission_map[tpl_id] = sub
            
            for tpl in templates:
                tpl_id = str(tpl.get("_id", ""))
                name = tpl.get("title", "Untitled")
                is_mandatory = tpl.get("isMandatory", False)
                marks = tpl.get("maximumMarks")
                allowed_types = tpl.get("allowedFileTypes") or []
                max_files = tpl.get("maxFiles", 1)
                admin_file = tpl.get("fileName")
                admin_url = tpl.get("fileUrl")
                
                sub = submission_map.get(tpl_id)
                if sub:
                    status = sub.get("status", "UNKNOWN")
                    if status == "APPROVED":
                        status_str = "✅ Approved"
                    elif status == "REJECTED":
                        status_str = "❌ Rejected"
                    else:
                        status_str = "⏳ Submitted"
                else:
                    status_str = "⬜ Not submitted"
                
                marks_str = f" [{marks} marks]" if marks else ""
                mandatory_str = " (mandatory)" if is_mandatory else " (optional)"
                lines.append(f"- {name}: {status_str}{marks_str}{mandatory_str}")
                if allowed_types:
                    lines.append(f"  Allowed formats: {', '.join(allowed_types)}")
                if max_files and max_files > 1:
                    lines.append(f"  Max files: {max_files}")
                if admin_file:
                    lines.append(f"  Admin template: {admin_file}")
                    if admin_url:
                        lines.append(f"  Template URL: {admin_url}")
        
        # Documents summary
        if submissions:
            approved = sum(1 for d in submissions if d.get("status") == "APPROVED")
            pending = sum(1 for d in submissions if d.get("status") in ("SUBMITTED", "PENDING", "RESUBMITTED"))
            rejected = sum(1 for d in submissions if d.get("status") == "REJECTED")
            lines.append(f"\n  Summary: {len(submissions)} submitted | {approved} approved | {pending} pending | {rejected} rejected")
        
        # Interactions
        interactions = list(get_collection("mentorstudentinteractions").find({"studentId": ObjectId(user_id)}))
        if interactions:
            lines.append("\n## Your Interactions")
            completed = sum(1 for i in interactions if i.get("status") == "COMPLETED")
            pending = sum(1 for i in interactions if i.get("status") in ("PENDING", "SCHEDULED"))
            lines.append(f"- Total: {len(interactions)} | Completed: {completed} | Pending: {pending}")
        
        # Attendance
        attendance = list(get_collection("studentattendances").find({"studentId": ObjectId(user_id)}))
        if attendance:
            lines.append("\n## Your Attendance")
            present = sum(1 for a in attendance if a.get("status") == "PRESENT")
            total = len(attendance)
            pct = round(present / total * 100, 1) if total > 0 else 0
            lines.append(f"- Delivered: {total} | Present: {present} | Absent: {total - present} | Percentage: {pct}%")
    else:
        lines.append("\nNo active enrollment found")
    
    return "\n".join(lines)


def _build_mentor_context(user_id: str) -> str:
    """Build comprehensive context for mentor role."""
    lines = ["## Your Info"]
    
    # User info
    user = get_collection("users").find_one({"_id": ObjectId(user_id)})
    if user:
        lines.append(f"- User ID: {user_id}")
        lines.append(f"- Name: {user.get('name', 'Unknown')}")
        lines.append(f"- Email: {user.get('email', 'N/A')}")
        lines.append(f"- Phone: {user.get('mobileNumber', 'N/A')}")
    
    # Get active session
    session = get_collection("academicyears").find_one({"isActive": True})
    if session:
        lines.append(f"\n## Your Current Session")
        lines.append(f"- Session: {session.get('name', 'Unknown')} (ID: {str(session['_id'])})")
    
    # Get assigned students
    assignments = list(get_collection("enrollmentmentorassignments").find(
        {"mentorId": ObjectId(user_id), "isActive": True}
    ).sort("assignedAt", -1))
    
    if assignments:
        lines.append(f"\n## Your Assigned Students ({len(assignments)})")
        lines.append("| Name | ID | Enrollment ID | Track | Status |")
        lines.append("|------|-----|---------------|-------|--------|")
        
        track_counts = {}
        for a in assignments:
            student = get_collection("users").find_one({"_id": a["studentId"]})
            enrollment = get_collection("studenttrackenrollments").find_one({"_id": a["enrollmentId"]})
            if student and enrollment:
                track = get_collection("tracksessionconfigs").find_one({"_id": enrollment["trackSessionConfigId"]})
                track_name = track.get("name", "Unknown") if track else "Unknown"
                lines.append(f"| {student.get('name', 'Unknown')} | {str(student['_id'])} | {str(enrollment['_id'])} | {track_name} | {enrollment.get('status')} |")
                track_counts[track_name] = track_counts.get(track_name, 0) + 1
        
        # Track summary
        if track_counts:
            lines.append("\n## Your Assigned Tracks")
            for track_name, count in track_counts.items():
                lines.append(f"- {track_name}: {count} students")
        
        # Track criteria flags
        track_configs = list(get_collection("tracksessionconfigs").find(
            {"_id": {"$in": [a.get("trackSessionConfigId") for a in assignments if a.get("trackSessionConfigId")]}}
        ))
        if track_configs:
            lines.append("\n## Track Criteria Flags")
            for tc in track_configs:
                components = tc.get("assessmentComponents", [])
                has_interactions = len(tc.get("interactionTemplates", [])) > 0
                has_attendance = any(c.get("type") == "ATTENDANCE" and c.get("isActive") for c in components)
                has_evaluations = any(c.get("type") in ("MENTOR_EVALUATION", "FINAL_YEAR_MENTOR_EVALUATION") and c.get("isActive") for c in components)
                has_doc_reviews = any(c.get("type") == "DOCUMENT" and c.get("isActive") for c in components)
                lines.append(f"- {tc.get('name', 'Track')}: hasInteractions={has_interactions}, hasAttendance={has_attendance}, hasEvaluations={has_evaluations}, hasDocumentReviews={has_doc_reviews}")
        
        # Pending work
        lines.append("\n## Pending Work")
        pending_interactions = 0
        pending_evaluations = 0
        pending_docs = 0
        for a in assignments:
            interactions = list(get_collection("mentorstudentinteractions").find({"enrollmentId": a["enrollmentId"], "status": {"$in": ["PENDING", "SCHEDULED"]}}))
            pending_interactions += len(interactions)
            evaluations = list(get_collection("mentorevaluationscores").find({"enrollmentId": a["enrollmentId"]}))
            pending_evaluations += max(0, len(assignments) - len(evaluations))
            docs = list(get_collection("trackonboardingsubmissions").find({"enrollmentId": a["enrollmentId"], "status": "SUBMITTED"}))
            pending_docs += len(docs)
        
        lines.append(f"- Pending Interactions: {pending_interactions}")
        lines.append(f"- Pending Evaluations: {pending_evaluations}")
        lines.append(f"- Pending Document Reviews: {pending_docs}")
    else:
        lines.append("\nNo assigned students found")
    
    return "\n".join(lines)


def _build_admin_context(user_id: str) -> str:
    """Build comprehensive context for admin role."""
    lines = ["## Your Info"]
    
    # User info
    user = get_collection("users").find_one({"_id": ObjectId(user_id)})
    if user:
        lines.append(f"- User ID: {user_id}")
        lines.append(f"- Name: {user.get('name', 'Unknown')}")
        lines.append(f"- Email: {user.get('email', 'N/A')}")
    
    # Active session
    session = get_collection("academicyears").find_one({"isActive": True})
    if session:
        lines.append(f"\n## Active Session")
        lines.append(f"- Session: {session.get('name', 'Unknown')} (ID: {str(session['_id'])})")
        lines.append(f"- Status: Active")
    
    # Quick stats
    lines.append("\n## Quick Stats")
    total_students = get_collection("users").count_documents({"roles": "STUDENT", "isActive": True})
    total_mentors = get_collection("users").count_documents({"roles": "MENTOR", "isActive": True})
    enabled_tracks = get_collection("tracksessionconfigs").count_documents({"isEnabled": True})
    pending_onboarding = get_collection("trackonboardingsubmissions").count_documents({"status": "SUBMITTED"})
    lines.append(f"- Total Students: {total_students}")
    lines.append(f"- Total Mentors: {total_mentors}")
    lines.append(f"- Enabled Tracks: {enabled_tracks}")
    lines.append(f"- Pending Onboarding Reviews: {pending_onboarding}")
    
    # Track breakdown
    if session:
        enrollments = list(get_collection("studenttrackenrollments").find({"sessionId": session["_id"]}))
        track_counts = {}
        for e in enrollments:
            track = get_collection("tracksessionconfigs").find_one({"_id": e["trackSessionConfigId"]})
            track_name = track.get("name", "Unknown") if track else "Unknown"
            if track_name not in track_counts:
                track_counts[track_name] = {"active": 0, "pending": 0, "inactive": 0}
            status = e.get("status", "")
            if status in ("ACTIVE", "ENROLLED"):
                track_counts[track_name]["active"] += 1
            elif status == "PENDING_ONBOARDING":
                track_counts[track_name]["pending"] += 1
            elif status == "INACTIVE":
                track_counts[track_name]["inactive"] += 1
        
        if track_counts:
            lines.append("\n## Track Breakdown")
            for track_name, counts in track_counts.items():
                total = counts["active"] + counts["pending"] + counts["inactive"]
                lines.append(f"- {track_name}: {total} students ({counts['active']} active, {counts['pending']} pending, {counts['inactive']} inactive)")
    
    # Interaction analytics
    interactions = list(get_collection("mentorstudentinteractions").find({}))
    if interactions:
        lines.append("\n## Interaction Analytics")
        completed = sum(1 for i in interactions if i.get("status") == "COMPLETED")
        pending = sum(1 for i in interactions if i.get("status") in ("PENDING", "SCHEDULED"))
        missed = sum(1 for i in interactions if i.get("status") == "MISSED")
        total = len(interactions)
        lines.append(f"- Total Interactions: {total}")
        lines.append(f"- Completed: {completed} ({round(completed/total*100, 1) if total > 0 else 0}%)")
        lines.append(f"- Pending: {pending} ({round(pending/total*100, 1) if total > 0 else 0}%)")
        lines.append(f"- Missed: {missed} ({round(missed/total*100, 1) if total > 0 else 0}%)")
    
    # Attendance overview
    attendance = list(get_collection("studentattendances").find({}))
    if attendance:
        lines.append("\n## Attendance Overview")
        present = sum(1 for a in attendance if a.get("status") == "PRESENT")
        total = len(attendance)
        pct = round(present / total * 100, 1) if total > 0 else 0
        lines.append(f"- Average Attendance Rate: {pct}%")
    
    # Faculty summary
    mentors_with_assignments = get_collection("enrollmentmentorassignments").distinct("mentorId", {"isActive": True})
    lines.append("\n## Faculty Summary")
    lines.append(f"- Active Mentors with Assignments: {len(mentors_with_assignments)}")
    
    return "\n".join(lines)


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

    # Look up trackId from tracksessionconfigs
    track_config = get_collection("tracksessionconfigs").find_one({"_id": enrollment["trackSessionConfigId"]})
    track_id = track_config.get("trackId") if track_config else None

    record = {
        "enrollmentId": ObjectId(enrollment_id),
        "studentId": enrollment["studentId"],
        "trackSessionConfigId": enrollment["trackSessionConfigId"],
        "trackId": track_id,
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

    # Look up the assignment ID
    assignment = get_collection("enrollmentmentorassignments").find_one(
        {"enrollmentId": ObjectId(enrollment_id), "mentorId": ObjectId(mentor_id), "isActive": True}
    )
    assignment_id = assignment["_id"] if assignment else None

    record = {
        "sessionId": enrollment["sessionId"],
        "enrollmentId": ObjectId(enrollment_id),
        "assignmentId": assignment_id,
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
    """
    List announcements for a user.

    Uses a multi-path query to handle all scenarios:
    1. User is in the denormalized recipientStatuses array (web-app created).
    2. Announcement has empty/missing recipientStatuses (WA-agent created).
    3. ALL_TRACKS announcement where user enrolled after creation.
    """
    try:
        page = max(1, int(page)) if page else 1
        page_size = min(max(1, int(page_size)) if page_size else 20, 100)

        if user_id:
            user_oid = ObjectId(user_id)
            role_upper = (user_role or "STUDENT").upper()
            # Normalize to match DB audience format (STUDENT -> STUDENTS, MENTOR -> MENTORS)
            if role_upper == "STUDENT":
                role_upper = "STUDENTS"
            elif role_upper == "MENTOR":
                role_upper = "MENTORS"

            query = {
                "recipientStatuses.userId": user_oid,
                "$or": [
                    {"status": "SENT"},
                    {"status": {"$exists": False}},
                ],
            }
        else:
            query = {
                "$or": [
                    {"status": "SENT"},
                    {"status": {"$exists": False}},
                ],
            }

        total = get_collection("announcements").count_documents(query)
        skip = (page - 1) * page_size

        # Use projection to exclude heavy fields and only keep current user's recipientStatuses
        if user_id:
            pipeline = [
                {"$match": query},
                {"$sort": {"createdAt": -1}},
                {"$skip": skip},
                {"$limit": page_size},
                {"$addFields": {
                    "recipientStatuses": {
                        "$filter": {
                            "input": "$recipientStatuses",
                            "as": "rs",
                            "cond": {"$eq": ["$$rs.userId", user_oid]}
                        }
                    },
                    "readBy": {
                        "$filter": {
                            "input": "$readBy",
                            "as": "rb",
                            "cond": {"$eq": ["$$rb.userId", user_oid]}
                        }
                    }
                }},
            ]
            items = list(get_collection("announcements").aggregate(pipeline))
        else:
            items = list(get_collection("announcements").find(query, {"readBy": 0}).skip(skip).limit(page_size).sort("createdAt", -1))

        # Extract the current user's recipient status from each announcement
        if user_id:
            for item in items:
                recipient = item.get("recipientStatuses", [None])[0] if item.get("recipientStatuses") else None
                item["readAt"] = recipient.get("readAt") if recipient else None
                item["recipientRole"] = recipient.get("role") if recipient else None
                read_entry = item.get("readBy", [None])[0] if item.get("readBy") else None
                item["isRead"] = read_entry is not None

        return {"items": _serialize(items), "total": total, "page": page, "pageSize": page_size}
    except Exception as e:
        # Fallback: try to return all announcements
        try:
            total = get_collection("announcements").count_documents({})
            items = list(get_collection("announcements").find({}).limit(20).sort("createdAt", -1))
            return {"items": _serialize(items), "total": total, "page": 1, "pageSize": 20, "warning": f"Query failed: {str(e)}"}
        except Exception:
            return {"items": [], "total": 0, "page": 1, "pageSize": 20, "error": str(e)}


def get_announcement(announcement_id: str) -> dict:
    return _serialize(get_collection("announcements").find_one({"_id": ObjectId(announcement_id)}))


def get_announcement_attachments(announcement_id: str) -> dict:
    """Get attachments (images, documents, videos) for an announcement."""
    ann = get_collection("announcements").find_one(
        {"_id": ObjectId(announcement_id)},
        {"attachments": 1, "title": 1}
    )
    if not ann:
        return {"error": "Announcement not found"}
    attachments = ann.get("attachments", [])
    return {
        "announcementId": announcement_id,
        "title": ann.get("title", ""),
        "attachments": _serialize(attachments),
        "count": len(attachments)
    }


def create_announcement(title: str, message: str, audience: str, creator_user_id: str,
                        track_scope: str = "ALL_TRACKS") -> dict:
    creator = get_collection("users").find_one({"_id": ObjectId(creator_user_id)})
    if not creator:
        return {"error": "Creator not found"}

    role_upper = (audience or "STUDENTS").upper()

    # Resolve recipients based on audience and track scope
    user_query: dict = {"isActive": True, "isDeleted": False}
    if role_upper == "STUDENTS":
        user_query["roles"] = "STUDENT"
    elif role_upper == "MENTORS":
        user_query["roles"] = "MENTOR"
    # BOTH → no roles filter

    candidate_users = list(get_collection("users").find(
        user_query,
        {"_id": 1, "name": 1, "email": 1, "roles": 1, "rollNumber": 1, "programme": 1, "section": 1}
    ))

    # Build recipientStatuses
    recipient_statuses = []
    now = datetime.utcnow()

    if track_scope == "ALL_TRACKS":
        # Include all matching candidates
        for u in candidate_users:
            user_role = "STUDENT" if "STUDENT" in u.get("roles", []) else "MENTOR"
            recipient_statuses.append({
                "userId": u["_id"],
                "role": user_role,
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "rollNumber": u.get("rollNumber"),
                "programme": u.get("programme"),
                "section": u.get("section"),
                "trackIds": [],
                "trackNames": [],
                "parentTrackIds": [],
                "parentTrackNames": [],
                "notificationId": None,
                "readAt": None,
                "emailQueuedAt": None,
                "emailMessageId": None,
            })
    else:
        # For SELECTED_TRACKS / UNASSIGNED_STUDENTS: filter by enrollment
        enrolled_student_ids = set()
        enrollments = list(get_collection("studenttrackenrollments").find(
            {"status": {"$in": ["ACTIVE", "ENROLLED"]}}
        ))
        for e in enrollments:
            enrolled_student_ids.add(e["studentId"])

        for u in candidate_users:
            uid = u["_id"]
            user_role = "STUDENT" if "STUDENT" in u.get("roles", []) else "MENTOR"

            if track_scope == "UNASSIGNED_STUDENTS":
                # Only students without an enrollment
                if user_role == "STUDENT" and uid in enrolled_student_ids:
                    continue
            elif track_scope == "SELECTED_TRACKS":
                # Only students with an enrollment (specific track filtering is complex;
                # include all enrolled students as a reasonable approximation)
                if user_role == "STUDENT" and uid not in enrolled_student_ids:
                    continue

            recipient_statuses.append({
                "userId": uid,
                "role": user_role,
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "rollNumber": u.get("rollNumber"),
                "programme": u.get("programme"),
                "section": u.get("section"),
                "trackIds": [],
                "trackNames": [],
                "parentTrackIds": [],
                "parentTrackNames": [],
                "notificationId": None,
                "readAt": None,
                "emailQueuedAt": None,
                "emailMessageId": None,
            })

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
        "recipientStatuses": recipient_statuses,
        "readBy": [],
        "recipientCount": len(recipient_statuses),
        "studentRecipientCount": sum(1 for r in recipient_statuses if r["role"] == "STUDENT"),
        "mentorRecipientCount": sum(1 for r in recipient_statuses if r["role"] == "MENTOR"),
        "readCount": 0,
        "createdAt": now,
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

def list_teams(session_id: str = None, track_config_id: str = None, member_id: str = None) -> list:
    query = {}
    if session_id:
        query["sessionId"] = ObjectId(session_id)
    if track_config_id:
        query["trackSessionConfigId"] = ObjectId(track_config_id)
    if member_id:
        query["memberIds"] = ObjectId(member_id)
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


# ============================================================
# STUDENT READ-ONLY DATA ACCESS
# ============================================================

def get_student_documents(student_id: str, enrollment_id: str = None) -> list:
    """Get all document templates with their latest submission status for a student."""
    
    # Find the active session
    active_session = get_collection("academicyears").find_one({"isActive": True})
    if not active_session:
        return _serialize([])
    
    # Find student's enrollment in active session
    if enrollment_id:
        enrollment = get_collection("studenttrackenrollments").find_one({"_id": ObjectId(enrollment_id)})
    else:
        enrollment = get_collection("studenttrackenrollments").find_one({
            "studentId": ObjectId(student_id),
            "sessionId": active_session["_id"],
            "status": "ACTIVE"
        })
    
    if not enrollment:
        return _serialize([])
    
    enrollment_oid = enrollment["_id"]
    
    # Get submissions for this enrollment only
    query = {
        "studentId": ObjectId(student_id),
        "enrollmentId": enrollment_oid,
        "submissionKind": "DOCUMENT"
    }
    submissions = list(get_collection("trackonboardingsubmissions").find(query).sort([
        ("documentTemplateId", 1),
        ("attemptNumber", -1),
        ("_id", -1),
    ]))
    
    # Get all active templates from this enrollment's track config and parents
    template_lookup = {}
    all_template_ids = []
    processed_configs = set()
    
    tc_id = enrollment.get("trackSessionConfigId")
    if tc_id:
        tc = get_collection("tracksessionconfigs").find_one({"_id": tc_id})
        if tc:
            # Add templates from this config
            for tmpl in tc.get("documentTemplates", []):
                if tmpl.get("isActive", True):
                    tid = str(tmpl.get("_id", ""))
                    template_lookup[tid] = {
                        "title": tmpl.get("title", "Unknown Document"),
                        "code": tmpl.get("code", ""),
                        "isMandatory": tmpl.get("isMandatory", False),
                    }
                    all_template_ids.append(tid)
            
            # Check for parent track
            track = get_collection("tracks").find_one({"_id": tc.get("trackId")})
            if track and track.get("parentTrackId"):
                parent_tc = get_collection("tracksessionconfigs").find_one({
                    "sessionId": tc.get("sessionId"),
                    "trackId": track["parentTrackId"]
                })
                if parent_tc:
                    for tmpl in parent_tc.get("documentTemplates", []):
                        if tmpl.get("isActive", True):
                            tid = str(tmpl.get("_id", ""))
                            if tid not in template_lookup:
                                template_lookup[tid] = {
                                    "title": tmpl.get("title", "Unknown Document"),
                                    "code": tmpl.get("code", ""),
                                    "isMandatory": tmpl.get("isMandatory", False),
                                }
                                all_template_ids.append(tid)
    
    # Keep only the latest submission per documentTemplateId
    seen_templates = set()
    latest_subs = []
    for sub in submissions:
        tid = str(sub.get("documentTemplateId", ""))
        # Skip submissions with orphaned template IDs (not in current track config)
        if tid not in template_lookup:
            continue
        if tid not in seen_templates:
            seen_templates.add(tid)
            # Treat DRAFT as NOT_SUBMITTED (matches web app behavior)
            if sub.get("status") == "DRAFT":
                sub["status"] = "NOT_SUBMITTED"
            # Enrich with template info
            tmpl_info = template_lookup.get(tid, {})
            sub["documentTitle"] = tmpl_info.get("title", sub.get("documentTemplateName", "Unknown Document"))
            sub["documentCode"] = tmpl_info.get("code", "")
            sub["isMandatory"] = tmpl_info.get("isMandatory", False)
            # Rename fileUrl to url for easier AI consumption
            if "files" in sub:
                for f in sub["files"]:
                    if "fileUrl" in f:
                        f["url"] = f.pop("fileUrl")
            latest_subs.append(sub)
    
    # Add templates with no submission as NOT_SUBMITTED
    for tid in all_template_ids:
        if tid not in seen_templates:
            tmpl_info = template_lookup[tid]
            latest_subs.append({
                "documentTitle": tmpl_info["title"],
                "documentCode": tmpl_info["code"],
                "isMandatory": tmpl_info["isMandatory"],
                "status": "NOT_SUBMITTED",
                "files": [],
            })
    
    return _serialize(latest_subs)


def get_student_document_summary(student_id: str, enrollment_id: str = None) -> dict:
    """Get document submission summary for a student with template titles."""
    docs = get_student_documents(student_id, enrollment_id)
    
    summary = {
        "total": len(docs),
        "approved": sum(1 for d in docs if d.get("status") == "APPROVED"),
        "pending": sum(1 for d in docs if d.get("status") == "SUBMITTED"),
        "rejected": sum(1 for d in docs if d.get("status") == "REJECTED"),
        "not_submitted": sum(1 for d in docs if d.get("status") == "NOT_SUBMITTED"),
        "documents": []
    }
    for doc in docs:
        files_info = []
        for f in doc.get("files", []):
            files_info.append({
                "url": f.get("url"),
                "fileName": f.get("fileName"),
                "fileSizeBytes": f.get("fileSizeBytes"),
                "contentType": f.get("contentType")
            })
        
        summary["documents"].append({
            "id": str(doc.get("_id", "")),
            "title": doc.get("documentTitle", "Unknown Document"),
            "code": doc.get("documentCode", ""),
            "status": doc.get("status"),
            "isMandatory": doc.get("isMandatory", False),
            "submittedAt": doc.get("submittedAt"),
            "reviewedAt": doc.get("reviewedAt"),
            "reviewComment": doc.get("reviewComment"),
            "awardedMarks": doc.get("awardedMarks"),
            "files": files_info,
            "rejectionItems": doc.get("rejectionItems", [])
        })
    return summary


def get_student_attendance_detail(student_id: str, enrollment_id: str = None) -> dict:
    """Get detailed attendance for a student."""
    query = {"studentId": ObjectId(student_id)}
    if enrollment_id:
        query["enrollmentId"] = ObjectId(enrollment_id)
    records = list(get_collection("studentattendances").find(query).sort("dateKey", -1))
    
    present = sum(1 for r in records if r.get("status") == "PRESENT")
    total = len(records)
    percentage = (present / total * 100) if total > 0 else 0
    
    return {
        "totalSlots": total,
        "present": present,
        "absent": total - present,
        "percentage": round(percentage, 1),
        "recentRecords": _serialize(records[:10])  # Last 10 records
    }


def get_student_interactions_detail(student_id: str, enrollment_id: str = None) -> dict:
    """Get interaction details for a student."""
    query = {"studentId": ObjectId(student_id)}
    if enrollment_id:
        query["enrollmentId"] = ObjectId(enrollment_id)
    interactions = list(get_collection("mentorstudentinteractions").find(query).sort("scheduledAt", -1))
    
    completed = [i for i in interactions if i.get("status") == "COMPLETED"]
    pending = [i for i in interactions if i.get("status") in ("PENDING", "SCHEDULED")]
    
    return {
        "total": len(interactions),
        "completed": len(completed),
        "pending": len(pending),
        "interactions": _serialize(interactions[:5])  # Last 5 interactions
    }


def get_student_score_summary(student_id: str, enrollment_id: str = None) -> dict:
    """Get score summary for a student."""
    query = {"studentId": ObjectId(student_id)}
    if enrollment_id:
        query["enrollmentId"] = ObjectId(enrollment_id)
    ledger = list(get_collection("enrollmentscoreledgers").find(query))
    
    by_component = {}
    for entry in ledger:
        comp_type = entry.get("componentType", "UNKNOWN")
        if comp_type not in by_component:
            by_component[comp_type] = {"marksAwarded": 0, "maxMarks": 0}
        by_component[comp_type]["marksAwarded"] += entry.get("marksAwarded", 0)
        by_component[comp_type]["maxMarks"] += entry.get("maxMarks", 0)
    
    total_awarded = sum(c["marksAwarded"] for c in by_component.values())
    total_max = sum(c["maxMarks"] for c in by_component.values())
    percentage = (total_awarded / total_max * 100) if total_max > 0 else 0
    
    return {
        "total": {"marksAwarded": total_awarded, "maxMarks": total_max, "percentage": round(percentage, 1)},
        "byComponent": by_component
    }


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


def submit_document_upload(
    student_id: str,
    document_template_id: str,
    file_url: str,
    object_key: str,
    file_name: str,
    file_size_bytes: int,
    content_type: str,
) -> dict:
    """Submit a previously uploaded document via the web app API.

    document_template_id can be:
    - A 24-char hex ObjectId (e.g., "6a0ac366c3247e48a174f396")
    - A template code (e.g., "DOC_MS1LI45R_XJF0UR") — resolved from tracksessionconfigs
    """
    import asyncio
    import jwt
    from datetime import datetime, timezone, timedelta
    from config import JWT_SECRET, WEBAPP_BASE_URL
    import httpx
    import re

    # Get student info for JWT
    student = get_collection("users").find_one({"_id": ObjectId(student_id)})
    if not student:
        return {"error": "Student not found"}

    # Resolve document_template_id: if not a valid ObjectId, look up by code
    template_id = document_template_id
    if not re.match(r"^[0-9a-fA-F]{24}$", document_template_id):
        # It's a code like "DOC_MS1LI45R_XJF0UR" — search in tracksessionconfigs
        session = get_collection("academicyears").find_one({"isActive": True})
        if session:
            enrollment = get_collection("studenttrackenrollments").find_one({
                "studentId": student["_id"],
                "sessionId": session["_id"],
                "status": "ACTIVE",
            })
            if enrollment:
                # Search all tracksessionconfigs for this template code
                all_tcs = get_collection("tracksessionconfigs").find({"sessionId": session["_id"]})
                for tc in all_tcs:
                    for tmpl in (tc.get("documentTemplates") or []):
                        if tmpl.get("code", "").upper() == document_template_id.upper():
                            template_id = str(tmpl["_id"])
                            break
                    if template_id != document_template_id:
                        break

        if template_id == document_template_id:
            return {"error": f"Could not find template with code '{document_template_id}'. Pass the ObjectId instead."}

    # Generate JWT
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(student["_id"]),
            "email": student.get("email", ""),
            "roles": student.get("roles", ["STUDENT"]),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        JWT_SECRET,
        algorithm="HS256",
    )

    # Call web app API
    url = f"{WEBAPP_BASE_URL}/api/student/tracks/onboarding/documents"
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"internship_token={token}",
    }
    payload = {
        "documentTemplateId": template_id,
        "files": [{
            "fileName": file_name,
            "fileUrl": file_url,
            "objectKey": object_key,
            "fileSizeBytes": int(file_size_bytes),
            "contentType": content_type,
        }],
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            data = resp.json()
            if resp.status_code in (200, 201):
                return {
                    "submission_id": str(data.get("item", {}).get("_id", "")),
                    "status": "PENDING",
                    "message": f"Document '{file_name}' submitted successfully.",
                }
            else:
                return {"error": data.get("message", f"Submission failed: {resp.status_code}")}
    except Exception as e:
        return {"error": f"Submission failed: {str(e)}"}


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
    "get_announcement_attachments": {
        "description": "Get attachments (images, documents, videos) for an announcement. Returns file URLs that can be sent to the user.",
        "params": {"announcement_id": "string"},
        "handler": get_announcement_attachments,
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
        "description": "List teams for a session, optionally filtered by track config or member",
        "params": {"session_id": "string (optional)", "track_config_id": "string (optional)", "member_id": "string (optional)"},
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
    },
    "get_student_documents": {
        "description": "Get document submissions for a student (read-only)",
        "params": {"student_id": "string", "enrollment_id": "string (optional)"},
        "handler": get_student_documents,
        "permission": "read",
        "collection": "trackonboardingsubmissions"
    },
    "get_student_document_summary": {
        "description": "Get document submission summary for a student (approved/pending/rejected counts)",
        "params": {"student_id": "string", "enrollment_id": "string (optional)"},
        "handler": get_student_document_summary,
        "permission": "read",
        "collection": "trackonboardingsubmissions"
    },
    "get_student_attendance_detail": {
        "description": "Get detailed attendance for a student (present/absent/percentage)",
        "params": {"student_id": "string", "enrollment_id": "string (optional)"},
        "handler": get_student_attendance_detail,
        "permission": "read",
        "collection": "studentattendances"
    },
    "get_student_interactions_detail": {
        "description": "Get interaction details for a student (completed/pending counts)",
        "params": {"student_id": "string", "enrollment_id": "string (optional)"},
        "handler": get_student_interactions_detail,
        "permission": "read",
        "collection": "mentorstudentinteractions"
    },
    "get_student_score_summary": {
        "description": "Get score summary for a student (marks by component type)",
        "params": {"student_id": "string", "enrollment_id": "string (optional)"},
        "handler": get_student_score_summary,
        "permission": "read",
        "collection": "enrollmentscoreledgers"
    },
    "submit_document_upload": {
        "description": "Submit a previously uploaded document (from WhatsApp) to a track onboarding. Use after a student sends a document file. document_template_id can be the template code (e.g. DOC_MS1LI45R_XJF0UR) from the context, or the 24-char ObjectId. This calls the web app API — not a direct DB write.",
        "params": {
            "student_id": "string",
            "document_template_id": "string",
            "file_url": "string",
            "object_key": "string",
            "file_name": "string",
            "file_size_bytes": "int",
            "content_type": "string"
        },
        "handler": submit_document_upload,
        "permission": "read",
        "collection": ""
    }
}


def execute_function(name: str, params: dict, user_role: str) -> dict:
    func = FUNCTIONS.get(name)
    if not func:
        return {"error": f"Unknown function: {name}"}

    # Check permission (skip if no collection — function doesn't touch DB directly)
    collection = func.get("collection", "")
    if collection:
        from agent.permissions import can_read, can_write
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
