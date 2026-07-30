# Functions: Mentor

## Summary
Mentor assignments, interactions, sessions, progress tracking. Use when query involves mentor, assign, interaction, session, progress.

---

## Assignment Operations

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_student_mentor` | Get a student's active mentor | `studentId?: string` | `{assigned, assignment, mentor}` | No |
| `get_mentor_assignments` | Get mentor's assigned students | `mentorId: string, session?: string` | `Assignment[]` | No |
| `assign_student_to_mentor` | Assign student to mentor | `enrollmentId: string, mentorId: string` | `Assignment` | Yes |
| `release_mentor_assignment` | Release assignment | `assignmentId: string, reason: string` | `Assignment` | Yes |

**Students:** Use `get_student_mentor` to check who your mentor is. No need to query raw collections.

## Interaction Operations

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_interactions` | List interactions | `enrollmentId?: string, mentorId?: string, filters?` | `Interaction[]` | No |
| `get_interaction` | Get interaction details | `interactionId: string` | `Interaction` | No |
| `create_interaction` | Create interaction | `interactionData: { enrollmentId, title, ... }` | `Interaction` | Yes |
| `update_interaction` | Update interaction | `interactionId: string, fields` | `Interaction` | Yes |
| `finalize_interaction` | Finalize with score | `interactionId: string, scores: Array, summary?: string` | `Interaction` | Yes |
| `mark_interaction_complete` | Mark as complete | `interactionId: string` | `Interaction` | Yes |

## Session Operations

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_interaction_sessions` | Get group sessions | `mentorId: string, filters?` | `InteractionSession[]` | No |
| `create_interaction_session` | Create session | `sessionData: { mentorId, trackConfigId, ... }` | `InteractionSession` | Yes |
| `finalize_session` | Finalize session | `sessionId: string, summary?: string` | `InteractionSession` | Yes |

## Progress Tracking

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_student_progress` | Get progress tracker | `assignmentId: string` | `StudentProgress` | No |
| `list_students_with_progress` | List students with progress | `mentorId: string` | `StudentWithProgress[]` | No |

---

## API Routes (Mentor)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/mentor/assigned-students` | List assigned students |
| GET | `/api/mentor/students-with-progress` | Students with progress |
| GET | `/api/mentor/interactions` | List interactions |
| POST | `/api/mentor/interactions` | Create interaction |
| PATCH | `/api/mentor/interactions/[interactionId]` | Update interaction |
| POST | `/api/mentor/interactions/[interactionId]/finalize` | Finalize interaction |
| POST | `/api/mentor/mark-interaction-complete` | Mark complete |
| POST | `/api/mentor/interaction-sessions/[sessionId]/finalize` | Finalize session |