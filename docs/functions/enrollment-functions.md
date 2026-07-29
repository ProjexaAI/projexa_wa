# Functions: Enrollment

## Summary
Enroll students, switch tracks, view scores. Use when query involves enrollment, enroll, switch, track, status.

---

## Enrollment Operations

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_enrollments` | List enrollments with filters | `filters: { studentId?, trackConfigId?, sessionId?, status?, page?, pageSize? }` | `{ items, total }` | No |
| `get_enrollment` | Get enrollment by ID | `enrollment_id: string` | `Enrollment` | No |
| `get_student_enrollments` | Get student's enrollments | `student_id: string, session?: string` | `Enrollment[]` | No |
| `create_enrollment` | Enroll student in track | `studentId: string, trackSessionConfigId: string` | `Enrollment` | Yes |
| `update_enrollment_status` | Change enrollment status | `enrollment_id: string, status: string, reason?: string` | `Enrollment` | Yes |
| `switch_enrollment` | Switch student to different track | `enrollment_id: string, toTrackSessionConfigId: string, reason: string` | `Enrollment` | Yes |
| `force_assign_to_track` | Force-assign student to a track config (admin override) | `configId: string, studentId: string, adminUserId: string, allowSameTrackReset?: boolean` | `{ createdEnrollmentId, switchedFromEnrollmentId }` | Yes |

## Score Operations

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_enrollment_scores` | Get score ledger for enrollment | `enrollment_id: string` | `ScoreLedger[]` | No |
| `get_score_summary` | Get score summary with totals | `enrollment_id: string` | `ScoreSummary` | No |

---

## API Routes (Student)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/student/tracks/score-summary` | Get score summary |
| GET | `/api/student/tracks/history` | Get track history |
| GET | `/api/student/tracks/switch-options` | Get track switch options |
| POST | `/api/student/tracks/switch-requests` | Submit track switch request |