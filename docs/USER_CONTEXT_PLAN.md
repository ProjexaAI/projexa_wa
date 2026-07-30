# User Context Plan

## Problem
The LLM has no user context beyond `user_id`, `name`, and `role`. It doesn't know the user's session, track, team, mentor, or what pages/data exist for their role. So it guesses or returns generic answers.

## Goal
Inject a **role-specific context block** into the system prompt that gives the LLM factual, pre-fetched data about the current user. This context is treated as ground truth — the LLM uses it directly in function calls instead of querying to find basic info.

## Design Principles
1. **Role-specific**: Each role gets only the data relevant to it
2. **Page-aware**: Context includes data needed to answer questions about ALL pages the role can access
3. **Pre-fetched**: Data is fetched once at the start of `process_message`, not via tool calls
4. **Cached**: 5-minute cache per user to avoid repeated DB hits
5. **Concise**: Plain text, not JSON — easy for the LLM to parse and reference
6. **Stable**: IDs are included so the LLM can use them directly in function calls

---

## Student Pages & Required Context

### Pages the student can access:
| Page | Route | Key Data |
|------|-------|----------|
| Dashboard | `/student` | Profile, team, mentor, attendance, interactions, scores, announcements |
| Documents | `/student/documents` | Document templates, submission status, approval status |
| Track & Scores | `/student/track` | Current track, score breakdown, switch history, switch options |
| Attendance | `/student/attendance` | Attendance summary, calendar, marks, QR scan sessions |
| Interactions | `/student/interactions` | Interaction timeline, upcoming sessions, completed sessions |
| Announcements | `/student/announcements` | Announcement list, unread count, detail view |

### Context block for STUDENT:
```
## Your Info
- User ID: 69f9c8decb5408f3886424e4
- Name: Harshit Singh
- Email: harshit@krmangalam.edu.in
- Roll Number: 2401010045
- Programme: B.Tech CSE
- Section: A
- Year: 2nd
- Profile Photo: https://cdn.projexa.ai/photos/harshit.jpg

## Your Enrollment
- Status: ACTIVE
- Session: Summer 2026 (ID: 685a...)
- Track: Full Stack Development (ID: 685b...)
- Track Mode: TEAM
- Enrollment ID: 686a...
- Onboarding: Completed

## Your Team
- Team: Projexa (ID: 686c...)
- Role: Leader
- Members:
  - Harshit Singh (ID: 69f9c8decb5408f3886424e4) — Leader
  - Kushagra Bhardwaj (ID: 69fa...) — Member

## Your Mentor
- Dr. Swati (ID: 687a...)
- Email: swati@krmangalam.edu.in
- Phone: 9911595412
- Assigned: 15 June 2026

## Your Track Criteria (Full Stack Development)
- Attendance: 15/20 (75%) — Active
- Interaction: 22/30 (73.3%) — Active, 3/5 completed
- Document: 8/10 (80%) — Active, 2/3 approved
- Mentor Evaluation: 33/40 (82.5%) — Active
- Total: 78/100 (78%)

## Your Documents
- Onboarding Documents: 3/3 approved
- Additional Documents: 1/2 approved, 1 pending review

## Your Interactions
- Upcoming: Interaction 4 (Scheduled: 5 Aug 2026)
- Completed: 3/5 (last: 28 July 2026)

## Your Attendance
- Delivered: 60 classes
- Present: 45 (75%)
- Marks: 15/20

## Recent Announcements
- Unread: 2
- Latest: "Mid-term Evaluation Schedule" (30 July 2026)
```

### DB queries for student context (8 queries):
1. `users` → name, email, rollNumber, programme, section, studentYear, profilePicture
2. `studenttrackenrollments` → active enrollment (status, sessionId, trackSessionConfigId, mentorId)
3. `teams` → team by memberId, memberIds, leaderId
4. `enrollmentmentorassignments` → mentor assignment (mentorId, assignedAt)
5. `internshipsessions` → session name
6. `tracksessionconfigs` → track name, mode, assessmentComponents, interactionTemplates, documentTemplates
7. `enrollmentscoreledgers` → current scores per component
8. `studentattendances` → attendance summary (present count, delivered count)

---

## Mentor Pages & Required Context

### Pages the mentor can access:
| Page | Route | Key Data |
|------|-------|----------|
| Dashboard | `/mentor/dashboard` | Stat cards, pending work, upcoming interactions |
| Students | `/mentor/students` | Student hierarchy, progress sidebar |
| Interactions | `/mentor/interactions` | Interaction rounds, session workspace, scoring |
| Attendance | `/mentor/attendance` | Attendance overview, live QR, scan records |
| Evaluations | `/mentor/evaluations` | Evaluation criteria, student scoring |
| Document Reviews | `/mentor/document-reviews` | Review queue, approve/reject docs |
| Announcements | `/mentor/announcements` | Created announcements, recipients |

### Context block for MENTOR:
```
## Your Info
- User ID: 687a...
- Name: Dr. Swati
- Email: swati@krmangalam.edu.in
- Phone: 9911595412

## Your Current Session
- Session: Summer 2026 (ID: 685a...)

## Your Assigned Tracks (2)
- Full Stack Development (Config ID: 685b..., 3 students)
- Data Science (Config ID: 685c..., 2 students)

## Your Assigned Students (5)
| Name | ID | Enrollment ID | Track | Status |
|------|-----|---------------|-------|--------|
| Harshit Singh | 69f9... | 686a... | Full Stack | ACTIVE |
| Kushagra Bhardwaj | 69fa... | 686b... | Full Stack | ACTIVE |
| Priya Patel | 69fb... | 686c... | Full Stack | ACTIVE |
| Rahul Verma | 69fc... | 686d... | Data Science | ACTIVE |
| Anjali Sharma | 69fd... | 686e... | Data Science | ACTIVE |

## Track Criteria Flags
- Full Stack Development: hasInteractions=true, hasAttendance=true, hasEvaluations=true, hasDocumentReviews=true
- Data Science: hasInteractions=true, hasAttendance=false, hasEvaluations=true, hasDocumentReviews=false

## Pending Work
- Pending Interactions: 3
- Pending Evaluations: 2
- Pending Document Reviews: 1
- Students Below 75% Attendance: 1 (Rahul Verma)

## Your Announcements
- Created: 3 (latest: "Assignment Deadline" — 29 July 2026)
- Total Recipients: 15
- Read Rate: 80%
```

### DB queries for mentor context (8 queries):
1. `users` → name, email, phone
2. `enrollmentmentorassignments` → all active assignments (studentId, enrollmentId, sessionId)
3. `studenttrackenrollments` → enrollment details (status, trackSessionConfigId)
4. `tracksessionconfigs` → track names, assessmentComponents, interactionTemplates
5. `mentorstudentinteractions` → pending/completed counts per student
6. `mentorevaluationscores` → pending evaluation counts
7. `studentdocument_submissions` → pending review counts
8. `studentattendances` → attendance summaries per student

---

## Admin Pages & Required Context

### Pages the admin can access:
| Page | Route | Key Data |
|------|-------|----------|
| Overview | `/admin` | System stats, enrollment breakdown, interaction analytics |
| Evaluation Analytics | `/admin/evaluation-analytics` | KPIs, track performance, mentor analytics, student insights |
| Onboarding Queue | `/admin/onboarding-queue` | Pending document reviews |
| Approved Teams | `/admin/approved-teams` | Team roster, document status |
| Track Switch Requests | `/admin/track-switch-requests` | Pending requests, risk assessment |
| Users | `/admin/users` | User list, profile options |
| Faculty | `/admin/faculty` | Faculty directory, assignment counts |
| Students | `/admin/students` | Hierarchical student list |
| Sessions | `/admin/sessions` | Academic sessions, year levels |
| Tracks | `/admin/tracks` | Track definitions, session configs |
| Interactions | `/admin/interactions` | Interaction templates, question sheets |
| Marks | `/admin/marks` | Student marks across criteria |
| Faculty Interactions | `/admin/faculty-interactions` | Mentor oversight |
| External Assessments | `/admin/external-assessments` | Email assessment requests |
| Announcements | `/admin/announcements` | Created announcements |
| Attendance | `/admin/attendance` | Attendance overview, per-track analytics |

### Context block for ADMIN:
```
## Your Info
- User ID: 680a...
- Name: Admin User
- Email: admin@krmangalam.edu.in

## Active Session
- Session: Summer 2026 (ID: 685a...)
- Status: Active
- Year Levels: 1st, 2nd, 3rd, 4th

## Quick Stats
- Total Students: 45
- Total Mentors: 8
- Enabled Tracks: 5
- Pending Onboarding Reviews: 3
- Pending Track Switch Requests: 2

## Track Breakdown
- Full Stack Development: 15 students (12 active, 2 pending, 1 inactive)
- Data Science: 12 students (10 active, 1 pending, 1 inactive)
- UI/UX Design: 8 students (7 active, 1 pending)
- Cloud Computing: 6 students (5 active, 1 pending)
- Cybersecurity: 4 students (4 active)

## Interaction Analytics
- Total Interactions: 120
- Completed: 85 (70.8%)
- Pending: 30 (25%)
- Missed: 5 (4.2%)
- Average Score: 72%

## Attendance Overview
- Average Attendance Rate: 82%
- Students Below 75%: 5
- Tracks with Attendance: Full Stack, Data Science (2 of 5)

## Evaluation Analytics
- Overall Average: 74%
- Pass Rate: 88%
- Distinction Rate: 15%
- Highest Performing Track: Full Stack (78%)
- Lowest Performing Track: Cybersecurity (68%)

## Faculty Summary
- Active Mentors: 8
- Mentors with Pending Work: 3
- Fully Complete Mentors: 5
```

### DB queries for admin context (9 queries):
1. `users` → counts by role (total students, total mentors)
2. `internshipsessions` → active session
3. `tracksessionconfigs` → enabled tracks count, track names
4. `studenttrackenrollments` → enrollment counts by status/track
5. `enrollmentmentorassignments` → mentor assignment counts
6. `teams` → team counts
7. `mentorstudentinteractions` → interaction analytics (total, completed, pending, missed)
8. `trackonboardingsubmissions` → pending review counts
9. `studentattendances` → attendance overview (average rate, students below threshold)

---

## Track Assessment Criteria

### What Are Assessment Components?

Each track (`TrackSessionConfig`) has an `assessmentComponents` array that defines **what criteria are used for scoring**. Not all tracks use all criteria. For example:
- A "Full Stack Development" track might have: ATTENDANCE (20 marks) + INTERACTION (30 marks) + DOCUMENT (10 marks) + MENTOR_EVALUATION (40 marks) = 100 total
- A "Research Project" track might have: INTERACTION (50 marks) + FINAL_EVALUATION (50 marks) = 100 total (no attendance, no documents)

### The 8 Assessment Component Types

| Code | Type | How Marks Are Computed | Example |
|------|------|----------------------|---------|
| `ATTENDANCE` | Attendance | Ratio-based: `(present / delivered) * maxMarks` | 45/60 classes present, maxMarks=20 → 15 marks |
| `INTERACTION` | Interaction | Sum of scored questions from mentor sessions | 3 interactions scored 8/10, 7/10, 9/10, maxMarks=30 → 24 marks |
| `DOCUMENT` | Document | Admin-entered marks on document approval | 2 docs approved with marks, maxMarks=10 → 8 marks |
| `MENTOR_EVALUATION` | Mentor Evaluation | Per-field scoring by mentor (configurable fields) | 4 fields scored, total 35/40, maxMarks=40 → 35 marks |
| `FINAL_YEAR_MENTOR_EVALUATION` | Final Year Mentor Eval | Same as MENTOR_EVALUATION, scoped to final-year students | Only for year 4 students |
| `FINAL_EVALUATION` | Final Evaluation (Rubric) | Score from evaluation events with rubric templates | Eval event scored 72/100, maxMarks=100 → 72 marks |
| `EMAIL` | Email Assessment | Score from external assessment forms sent via email | External org submits score, maxMarks=20 → 15 marks |
| `MANUAL` | Manual | Admin-entered penalties (negative marks) | -5 penalty for plagiarism |

### How Components Are Configured Per Track

Each `EmbeddedAssessmentComponent` in `TrackSessionConfig.assessmentComponents` has:

| Field | Purpose |
|-------|---------|
| `code` | Unique code (e.g., "ATT-01", "INTERACT1") |
| `title` | Display name (e.g., "Attendance Marks") |
| `type` | One of the 8 types above |
| `maxMarks` | Maximum marks for this component |
| `yearMarks` | Per-year override (e.g., `{1: 15, 2: 20}` — year 1 gets 15 max, year 2 gets 20) |
| `yearLevels` | Which years this applies to (empty = all years) |
| `isActive` | Whether the component is currently enabled |
| `rolloverPolicy` | "NONE" or "PERCENTAGE_TO_CURRENT_COMPONENT" (carry over marks from previous track) |
| `attendanceStartDate` / `attendanceEndDate` | Date window for attendance tracking |
| `mentorEvaluationFields` | Per-field config for MENTOR_EVALUATION type |

### How Feature Flags Are Derived

The WhatsApp bot needs to know which criteria are active to answer questions accurately:

```python
# From track's assessmentComponents:
has_attendance = any(c["type"] == "ATTENDANCE" and c["isActive"] for c in components)
has_interactions = len(track.interactionTemplates) > 0
has_evaluations = any(c["type"] in ("MENTOR_EVALUATION", "FINAL_YEAR_MENTOR_EVALUATION") and c["isActive"] for c in components)
has_document_reviews = any(c["type"] == "DOCUMENT" and c["isActive"] for c in components)
```

**Why this matters for the WhatsApp bot:**
- If `has_attendance = false`, don't say "your attendance is 85%" — say "attendance is not tracked for your track"
- If `has_evaluations = false`, don't say "you have pending evaluations" — say "mentor evaluation is not configured for your track"
- If `has_interactions = false`, don't ask about "interaction sessions"

### Score Summary Structure

The `getStudentTrackScoreSummary()` function returns:

```
totals: { marksAwarded: 78, maxMarks: 100, percentage: 78.0 }
byComponent: [
  { componentType: "ATTENDANCE", marksAwarded: 15, maxMarks: 20 },
  { componentType: "DOCUMENT", marksAwarded: 8, maxMarks: 10 },
  { componentType: "INTERACTION", marksAwarded: 22, maxMarks: 30 },
  { componentType: "RUBRIC", marksAwarded: 33, maxMarks: 40 }
]
byAssessmentComponent: [
  { componentCode: "ATT-01", componentTitle: "Attendance", componentType: "ATTENDANCE", marksAwarded: 15, maxMarks: 20, percentage: 75.0 },
  { componentCode: "DOC-01", componentTitle: "Document Submission", componentType: "DOCUMENT", marksAwarded: 8, maxMarks: 10, percentage: 80.0 },
  ...
]
```

### Important: `maxTotalMarks` and Year-Level Marks

- `maxTotalMarks` is a configurable ceiling (default 100, min 1, max 1000)
- Sum of all active component `maxMarks` must not exceed `maxTotalMarks`
- Components can have **year-specific maxMarks** via `yearMarks` map:
  - Example: Attendance has `yearMarks: { "1": 15, "2": 20, "3": 25, "4": 30 }`
  - A year-1 student gets 15 max marks for attendance, year-2 gets 20
- The WhatsApp bot should use the **effective maxMarks** for the student's year, not the default

---

## Implementation Plan

### Step 1: Create role-specific context builders in `functions.py`

```python
def get_user_context(user_id: str, role: str) -> str:
    """Build role-specific context string."""
    if role == "STUDENT":
        return _build_student_context(user_id)
    elif role == "MENTOR":
        return _build_mentor_context(user_id)
    elif role == "ADMIN":
        return _build_admin_context(user_id)
    return ""
```

### Step 2: Implement `_build_student_context(user_id)`

**Collections to query** (8 queries, parallel where possible):
1. `users` → basic info (name, email, rollNumber, programme, section, studentYear, profilePicture)
2. `studenttrackenrollments` → active enrollment (status, sessionId, trackSessionConfigId, mentorId)
3. `teams` → team by memberId, memberIds, leaderId
4. `enrollmentmentorassignments` → mentor assignment (mentorId, assignedAt)
5. `internshipsessions` → session name
6. `tracksessionconfigs` → track name, mode, assessmentComponents, interactionTemplates
7. `enrollmentscoreledgers` → current scores per component (for score summary)
8. `studentattendances` → attendance summary (present count, delivered count)

**Track criteria logic:**
- For each active assessment component in `tracksessionconfigs.assessmentComponents`:
  - If type is `ATTENDANCE`: fetch attendance summary from `studentattendances`
  - If type is `INTERACTION`: count completed/total from `enrollmentscoreledgers`
  - If type is `DOCUMENT`: count approved/total from `enrollmentscoreledgers`
  - If type is `MENTOR_EVALUATION`: get latest score from `enrollmentscoreledgers`
- Compute `marksAwarded` for each component using the same logic as `getStudentTrackScoreSummary()`

### Step 3: Implement `_build_mentor_context(user_id)`

**Collections to query** (8 queries):
1. `users` → basic info (name, email, phone)
2. `enrollmentmentorassignments` → all active assignments (studentId, enrollmentId, sessionId)
3. `studenttrackenrollments` → enrollment details (status, trackSessionConfigId)
4. `tracksessionconfigs` → track names, assessmentComponents, interactionTemplates
5. `mentorstudentinteractions` → pending/completed counts per student
6. `mentorevaluationscores` → pending evaluation counts
7. `studentdocument_submissions` → pending review counts
8. `studentattendances` → attendance summaries per student

**Track criteria logic:**
- For each assigned track, compute feature flags:
  - `hasInteractions`: `len(track.interactionTemplates) > 0`
  - `hasAttendance`: `any(c["type"] == "ATTENDANCE" and c["isActive"] for c in track.assessmentComponents)`
  - `hasEvaluations`: `any(c["type"] in ("MENTOR_EVALUATION", "FINAL_YEAR_MENTOR_EVALUATION") and c["isActive"] for c in track.assessmentComponents)`
  - `hasDocumentReviews`: `any(c["type"] == "DOCUMENT" and c["isActive"] for c in track.assessmentComponents)`
- For pending work counts, filter by track flags (don't count pending evaluations if hasEvaluations=false)

### Step 4: Implement `_build_admin_context(user_id)`

**Collections to query** (9 queries):
1. `users` → counts by role (total students, total mentors)
2. `internshipsessions` → active session
3. `tracksessionconfigs` → enabled tracks count, track names
4. `studenttrackenrollments` → enrollment counts by status/track
5. `enrollmentmentorassignments` → mentor assignment counts
6. `teams` → team counts
7. `mentorstudentinteractions` → interaction analytics (total, completed, pending, missed)
8. `trackonboardingsubmissions` → pending review counts
9. `studentattendances` → attendance overview (average rate, students below threshold)

**Track criteria logic:**
- For interaction analytics: count interactions by status (COMPLETED, PENDING, MISSED)
- For attendance overview: compute average attendance rate across all students, count students below 75%
- For tracks with attendance: filter tracks that have `ATTENDANCE` component in their assessmentComponents

### Step 5: Update `build_system_prompt` in `prompts.py`

- Accept `user_context: str` parameter
- Inject it as `## Your Info` block after `## User Context`
- Add Rule 14: "Use the Your Info section above — these are facts about the current user. Use IDs directly in function calls."

### Step 6: Update `process_message` in `core.py`

- Call `get_user_context(user_id, user_role)` before building system prompt
- Pass result to `build_system_prompt`

### Step 7: Cache invalidation

- Cache key: `context:{user_id}`
- TTL: 5 minutes
- Invalidate on: team join/leave, mentor assignment, enrollment status change

---

## What NOT to Include

- **Full enrollment list** (too verbose — just the active one)
- **All announcements** (fetched via tool calls when needed)
- **All attendance records** (fetched via tool calls when needed)
- **Historical data** (only current/recent)
- **Sensitive data** (passwords, internal flags)
- **Full student list for mentor** (just names + IDs + enrollment IDs — details fetched on demand)
- **All admin pages data** (just summary stats — details fetched on demand)

---

## Files to Modify

1. `agent/functions.py` — Add `get_user_context(user_id, role)` with 3 role-specific builders
2. `agent/prompts.py` — Update `build_system_prompt` to accept and inject `user_context`
3. `agent/core.py` — Call `get_user_context` in `process_message`
4. `docs/USER_CONTEXT_PLAN.md` — This file (planning doc)

---

## Verification Checklist

After implementation, test these queries for each role:

### Student
- [ ] "My team members" → returns correct team with members
- [ ] "Who is my mentor?" → returns correct mentor
- [ ] "My attendance" → uses enrollment ID directly, shows correct percentage
- [ ] "My scores" → uses enrollment ID directly, shows breakdown by component
- [ ] "Announcements for my track" → uses session + track config ID
- [ ] "What criteria are graded in my track?" → returns active assessment components with maxMarks
- [ ] "How much is attendance worth?" → returns attendance maxMarks (e.g., "20 marks")
- [ ] "My interaction score" → returns interaction marks/total
- [ ] "Show my document status" → returns pending/approved/rejected counts
- [ ] "When is my next interaction?" → returns upcoming interaction date

### Mentor
- [ ] "List my students" → returns all assigned students
- [ ] "Show Harshit's progress" → uses enrollment ID directly
- [ ] "Schedule interaction" → uses mentor + enrollment IDs
- [ ] "How many students are inactive?" → filters from pre-fetched list
- [ ] "Pending evaluations" → returns correct count (0 if hasEvaluations=false)
- [ ] "Which tracks have attendance?" → returns tracks where hasAttendance=true
- [ ] "Students below 75% attendance" → only shows if hasAttendance=true
- [ ] "Show document review queue" → returns pending docs count
- [ ] "Create announcement" → uses track IDs for audience targeting

### Admin
- [ ] "How many students?" → returns correct count
- [ ] "List all mentors" → uses session ID directly
- [ ] "Show team overview" → uses session + track config ID
- [ ] "Enrollment by track" → returns breakdown
- [ ] "Pending onboarding reviews" → returns correct count
- [ ] "Interaction completion rate" → returns total/completed/pending/missed
- [ ] "Average attendance rate" → returns percentage
- [ ] "Which tracks have attendance?" → returns list of tracks with ATTENDANCE component
- [ ] "Evaluation analytics" → returns KPIs (average, pass rate, distinction rate)
- [ ] "Faculty overview" → returns active/assigned/unassigned counts
