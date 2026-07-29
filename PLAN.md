# Projexa AI Agent - Master Plan

## Overview

An AI assistant for WhatsApp that can read/write data from the Projexa Internship Management System. Uses predefined functions for common operations and generates MongoDB queries for anything else. Enforces role-based permissions server-side to prevent jailbreaking.

---

## Platform: WhatsApp

The agent runs on WhatsApp. Users can:
- Send text messages (queries, commands)
- Send photos (document submissions, profile photos)
- Receive text responses, PDFs, images

**NOT supported from WhatsApp:**
- QR code scanning (attendance uses manual marking)
- Complex Excel exports (responses are text/PDF)
- Bulk operations (one-at-a-time via chat)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         REQUEST FLOW                                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. Request arrives: { query, user_token }                           │
│                          │                                           │
│  2. Auth Middleware ──────┤                                           │
│     - Validate JWT token                                             │
│     - Extract user_id, role                                          │
│     - Determine allowed_collections (read/write)                     │
│                          │                                           │
│  3. AI Agent ◄───────────┘                                           │
│     - Receives: query + user_role + allowed_collections              │
│     - ALL docs loaded into context (schema + functions + enums)      │
│     - Decides: predefined function OR custom MongoDB read query      │
│                          │                                           │
│  4. Executor                                                         │
│     - If predefined function → validate params → execute             │
│     - If custom query → validate READ-ONLY → execute                 │
│     - REJECT if write attempted via custom query                     │
│                          │                                           │
│  5. Return result to user                                            │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Key Principles

1. **Permission enforcement is SERVER-SIDE, not AI-side** - AI cannot bypass permissions via prompt injection
2. **Writes only via predefined functions** - No raw write queries allowed
3. **Reads via functions OR custom queries** - Custom queries are validated to be read-only
4. **Minimize query generation** - Cover all common operations as predefined functions
5. **All docs included in every request** - Total ~36KB (~9K tokens), fits easily in MiMo V2.5 Free's 200K context. No doc selection logic needed.

---

## Directory Structure

```
ai-agent/
├── PLAN.md                          # This file
├── docs/
│   ├── README.md                    # Index with doc summaries
│   ├── schema/
│   │   ├── core.md                  # User, AcademicYear, Track, TrackSessionConfig, Enrollment
│   │   ├── attendance.md            # StudentAttendance, AttendanceScanSession/Event
│   │   ├── evaluation.md            # ScoreLedger, EvaluationScore, EvaluationEvent
│   │   ├── mentor.md                # Interactions, Assignments, Progress
│   │   ├── onboarding.md            # Document/Intake submissions
│   │   ├── teams.md                 # Teams, Invitations
│   │   ├── notifications.md         # Notifications, Announcements
│   │   └── misc.md                  # Support tickets, OTPs, settings, audit logs
│   ├── functions/
│   │   ├── auth-functions.md        # Login, session, profile
│   │   ├── user-functions.md        # User CRUD
│   │   ├── track-functions.md       # Track CRUD, config
│   │   ├── enrollment-functions.md  # Enroll, switch, status
│   │   ├── attendance-functions.md  # Mark, view attendance
│   │   ├── evaluation-functions.md  # Score, evaluate
│   │   ├── mentor-functions.md      # Assignments, interactions
│   │   ├── announcement-functions.md # Create, read
│   │   ├── notification-functions.md # List, mark read
│   │   ├── team-functions.md        # Create, join, invite
│   │   ├── onboarding-functions.md  # Submit docs, intake
│   │   └── admin-functions.md       # User mgmt, simple admin
│   └── enums.md                     # All enum constants
├── agent/
│   ├── __init__.py
│   ├── core.py                      # Main agent loop (GPT-4 function calling)
│   ├── db.py                        # PyMongo connection
│   ├── permissions.py               # Role → collection mapping
│   ├── functions.py                 # Function registry + executor
│   ├── prompts.py                   # System prompts
│   └── validators.py                # Input validation
└── server.py                        # FastAPI endpoint
```

---

## Permissions Matrix

### ADMIN
- **Read:** ALL collections
- **Write:** ALL collections

### MENTOR
- **Read:**
  - `users` (limited fields)
  - `studenttrackenrollments`
  - `enrollmentmentorassignments`
  - `studentattendances`
  - `attendantscanevents`
  - `attendantscansessions`
  - `mentorstudentinteractions`
  - `mentorinteractionsessions`
  - `mentorinteractionsessionstudents`
  - `studentprogresses`
  - `mentorevaluationscores`
  - `mentorevaluationfieldconfigs`
  - `tracks`
  - `tracksessionconfigs`
  - `notifications`
  - `announcements`
  - `supporttickets` (own students only)
  - `enrollmentscoreledgers` (own students only)
- **Write:**
  - `studentattendances`
  - `attendantscanevents`
  - `attendantscansessions`
  - `mentorstudentinteractions`
  - `mentorinteractionsessions`
  - `mentorinteractionsessionstudents`
  - `mentorevaluationscores`
  - `mentorevaluationfieldconfigs`
  - `studentprogresses`
  - `notifications` (limited)

### STUDENT
- **Read:**
  - `users` (own profile only)
  - `tracks`
  - `tracksessionconfigs`
  - `studenttrackenrollments` (own only)
  - `studentattendances` (own only)
  - `mentorstudentinteractions` (own only)
  - `enrollmentmentorassignments` (own only)
  - `enrollmentscoreledgers` (own only)
  - `notifications` (own only)
  - `announcements`
  - `teams`
  - `teaminvitations` (own only)
  - `supporttickets` (own only)
  - `studentprofessionalprofiles` (own only)
- **Write:**
  - `supporttickets` (create own)
  - `teams` (create/join)
  - `teaminvitations` (respond)
  - `studentprofessionalprofiles` (update own)

---

## Predefined Functions

### Auth Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `login` | Authenticate user | email, password | JWT token | No |
| `get_current_user` | Get logged-in user profile | token | User object | No |
| `refresh_token` | Refresh JWT token | token | New token | No |

### User Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_user_by_id` | Fetch user by ID | user_id | User object | No |
| `get_user_by_email` | Fetch user by email | email | User object | No |
| `list_users` | List users with filters | role, session, pagination | User list | No |
| `create_user` | Create new user | user_data | User object | Yes |
| `update_user` | Update user fields | user_id, fields | User object | Yes |
| `bulk_import_users` | Import users from Excel | file_data, session | Import result | Yes |
| `delete_user` | Soft delete user | user_id | Success boolean | Yes |

### Track Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_tracks` | List all tracks | filters | Track list | No |
| `get_track` | Get track by ID | track_id | Track object | No |
| `get_track_by_code` | Get track by code | code | Track object | No |
| `create_track` | Create new track | track_data | Track object | Yes |
| `update_track` | Update track | track_id, fields | Track object | Yes |
| `get_track_config` | Get session config | session_id, track_id | Config object | No |
| `update_track_config` | Update config | config_id, fields | Config object | Yes |

### Enrollment Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_enrollments` | List enrollments | filters, pagination | Enrollment list | No |
| `get_enrollment` | Get enrollment by ID | enrollment_id | Enrollment object | No |
| `get_student_enrollments` | Get student's enrollments | student_id, session | Enrollment list | No |
| `create_enrollment` | Enroll student | student_id, track_config_id | Enrollment object | Yes |
| `update_enrollment_status` | Change status | enrollment_id, status | Enrollment object | Yes |
| `switch_enrollment` | Switch track | enrollment_id, to_config_id | Enrollment object | Yes |
| `get_enrollment_scores` | Get score ledger | enrollment_id | Score list | No |

### Attendance Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `mark_attendance` | Mark single attendance | enrollment_id, date, status, session | Attendance object | Yes |
| `bulk_mark_attendance` | Mark for multiple students | enrollment_ids, date, status, session | Attendance list | Yes |
| `get_student_attendance` | Get student's attendance | student_id, session, date_range | Attendance list | No |
| `get_session_attendance` | Get all attendance for session | session_config_id, date, session | Attendance list | No |
| `start_scan_session` | Start QR scan session | track_config_id, date, session | Scan session object | Yes |
| `end_scan_session` | End QR scan session | session_id | Scan session object | Yes |
| `record_scan_event` | Record QR scan | session_id, student_id, scan_data | Scan event object | Yes |
| `get_attendance_stats` | Get attendance statistics | enrollment_id or track_config_id | Stats object | No |

### Evaluation Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_score_ledger` | Get scores for enrollment | enrollment_id | Score list | No |
| `record_score` | Record a score | enrollment_id, component_type, marks | Score object | Yes |
| `bulk_record_scores` | Record scores in batch | scores_data | Score list | Yes |
| `get_evaluation_event` | Get evaluation event | event_id | Event object | No |
| `list_evaluation_events` | List events | filters | Event list | No |
| `create_evaluation_event` | Create event | event_data | Event object | Yes |
| `update_participant_score` | Update participant score | event_id, enrollment_id, score | Event object | Yes |
| `get_mentor_eval_scores` | Get mentor eval scores | enrollment_id or mentor_id | Score list | No |
| `submit_mentor_evaluation` | Submit eval | enrollment_id, fields, marks | Score object | Yes |

### Mentor Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_mentor_assignments` | Get mentor's students | mentor_id, session | Assignment list | No |
| `assign_student_to_mentor` | Assign student | enrollment_id, mentor_id | Assignment object | Yes |
| `release_mentor_assignment` | Release assignment | assignment_id, reason | Assignment object | Yes |
| `list_interactions` | List interactions | enrollment_id or mentor_id, filters | Interaction list | No |
| `get_interaction` | Get interaction | interaction_id | Interaction object | No |
| `create_interaction` | Create interaction | interaction_data | Interaction object | Yes |
| `update_interaction` | Update interaction | interaction_id, fields | Interaction object | Yes |
| `finalize_interaction` | Finalize with score | interaction_id, scores | Interaction object | Yes |
| `get_interaction_sessions` | Get group sessions | mentor_id, filters | Session list | No |
| `create_interaction_session` | Create session | session_data | Session object | Yes |
| `get_student_progress` | Get progress tracker | assignment_id | Progress object | No |

### Announcement Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_announcements` | List announcements | filters, pagination | Announcement list | No |
| `get_announcement` | Get announcement | announcement_id | Announcement object | No |
| `create_announcement` | Create announcement | announcement_data | Announcement object | Yes |
| `mark_announcement_read` | Mark as read | announcement_id, user_id | Success boolean | Yes |

### Notification Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_notifications` | List user notifications | user_id, filters | Notification list | No |
| `get_unread_count` | Get unread count | user_id | Count | No |
| `mark_notification_read` | Mark read | notification_id | Success boolean | Yes |
| `create_notification` | Create notification | notification_data | Notification object | Yes |

### Team Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_teams` | List teams | session, track_config | Team list | No |
| `get_team` | Get team | team_id | Team object | No |
| `create_team` | Create team | team_data | Team object | Yes |
| `join_team` | Join via invite code | invite_code, student_id | Team object | Yes |
| `invite_to_team` | Send invitation | team_id, invitee_id | Invitation object | Yes |
| `respond_to_invitation` | Accept/decline | invitation_id, response | Invitation object | Yes |

### Onboarding Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_onboarding_status` | Get onboarding status | enrollment_id | Status object | No |
| `submit_document` | Submit document | enrollment_id, template_id, files | Submission object | Yes |
| `submit_intake_form` | Submit intake form | enrollment_id, template_id, responses | Submission object | Yes |
| `review_submission` | Review submission | submission_id, decision, comment | Submission object | Yes |
| `get_submissions` | List submissions | enrollment_id or filters | Submission list | No |

### Admin Functions
| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_admin_dashboard` | Dashboard stats | session_id | Dashboard object | No |
| `list_audit_logs` | List audit logs | filters, pagination | Log list | No |
| `get_mentor_students` | Get mentor's students hierarchy | mentor_id, session | Hierarchy | No |
| `get_faculty_list` | List faculty members | filters | Faculty list | No |
| `get_placement_settings` | Get placement config | - | Settings object | No |
| `update_placement_settings` | Update placement config | fields | Settings object | Yes |
| `bulk_update_students` | Bulk update student fields | student_ids, fields | Result | Yes |
| `export_data` | Export to Excel | filters, format | File URL | No |

---

## MongoDB Query Validation (Read-Only)

Custom queries must pass validation:
1. Only `find()`, `findOne()`, `aggregate()` allowed
2. No `$set`, `$unset`, `$push`, `$pull`, `$inc`, `$rename` operators
3. No `insertOne`, `insertMany`, `updateOne`, `updateMany`, `deleteOne`, `deleteMany`
4. Collection must be in user's allowed_read list
5. Query timeout: 5 seconds max

---

## Implementation Phases

### Phase 1: Documentation (Current)
- [x] Create PLAN.md
- [ ] Create doc summaries (README.md)
- [ ] Split schema into domain docs
- [ ] Document all functions with params/returns
- [ ] Document enums

### Phase 2: Python Agent
- [ ] Set up project (requirements.txt, structure)
- [ ] Implement db.py (PyMongo connection)
- [ ] Implement permissions.py (role-based access)
- [ ] Implement functions.py (function registry)
- [ ] Implement core.py (GPT-4 function calling)
- [ ] Implement validators.py (query validation)

### Phase 3: Server
- [ ] FastAPI endpoint
- [ ] JWT auth middleware
- [ ] Request logging
- [ ] Error handling

### Phase 4: Testing
- [ ] Unit tests for permissions
- [ ] Unit tests for function executor
- [ ] Integration tests with MongoDB
- [ ] Security tests (jailbreak attempts)
