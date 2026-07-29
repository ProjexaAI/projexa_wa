# Projexa AI Agent - Documentation Index

## How This Works

All docs below are loaded into MiMo V2.5 Free (via OpenCode) context for every request. The AI reads the user's query and either:
1. Calls a predefined function (for common operations)
2. Generates a MongoDB read query (for anything else)

Writes can ONLY happen via predefined functions.

---

## Schema Docs (Database Structure)

| Doc | What It Covers | Collections |
|-----|----------------|-------------|
| [schema/core.md](schema/core.md) | Users, tracks, sessions, enrollments | `users`, `academicyears`, `tracks`, `tracksessionconfigs`, `studenttrackenrollments` |
| [schema/attendance.md](schema/attendance.md) | Attendance records | `studentattendances` |
| [schema/evaluation.md](schema/evaluation.md) | Scores, evaluations | `enrollmentscoreledgers`, `mentorevaluationscores`, `trackevaluationevents` |
| [schema/mentor.md](schema/mentor.md) | Mentor assignments, interactions | `enrollmentmentorassignments`, `mentorstudentinteractions`, `mentorinteractionsessions`, `studentprogresses` |
| [schema/onboarding.md](schema/onboarding.md) | Document/intake submissions | `trackonboardingsubmissions` |
| [schema/teams.md](schema/teams.md) | Teams, invitations | `teams`, `teaminvitations` |
| [schema/notifications.md](schema/notifications.md) | Notifications, announcements | `notifications`, `announcements` |
| [schema/misc.md](schema/misc.md) | Placement settings, external verification | `placementsettings`, `externalmentorverifications`, `emailassessmentrequests` |

---

## Functions Docs (Predefined Operations)

| Doc | What It Covers |
|-----|----------------|
| [functions/user-functions.md](functions/user-functions.md) | Get/update users |
| [functions/track-functions.md](functions/track-functions.md) | List/get tracks and configs |
| [functions/enrollment-functions.md](functions/enrollment-functions.md) | Enroll, switch, view enrollments |
| [functions/attendance-functions.md](functions/attendance-functions.md) | Mark and view attendance |
| [functions/evaluation-functions.md](functions/evaluation-functions.md) | Record and view scores |
| [functions/mentor-functions.md](functions/mentor-functions.md) | Assignments, interactions, sessions |
| [functions/announcement-functions.md](functions/announcement-functions.md) | Create and view announcements |
| [functions/notification-functions.md](functions/notification-functions.md) | View and mark notifications |
| [functions/team-functions.md](functions/team-functions.md) | Create/join teams |
| [functions/onboarding-functions.md](functions/onboarding-functions.md) | Submit docs and intake forms |
| [functions/admin-functions.md](functions/admin-functions.md) | Simple admin operations |

---

## Reference

| Doc | What It Covers |
|-----|----------------|
| [enums.md](enums.md) | All enum constants (roles, statuses, types) |

---

## What's NOT Included (Intentionally Removed)

These operations don't make sense for WhatsApp:
- QR scan attendance (can't scan QR from phone camera via WhatsApp)
- Complex admin dashboards (use the web app for that)
- Template management (rubrics, eligibility rules - admin does from web)
- Audit logs, role transfers (admin web operations)
- Faculty interaction oversight (admin web analytics)
- Support tickets (not implemented yet)
