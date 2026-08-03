# Functions: Evaluation & Scoring

## Summary
Score recording, score queries, mentor evaluations. Use when query involves score, evaluate, marks, grading.

---

## Score Recording

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `record_score` | Record a score entry | `enrollmentId: string, componentType: string, marks: number, maxMarks: number` | `ScoreLedger` | Yes |
| `update_component_mark` | Upsert a component mark | `enrollmentId: string, componentId: string, marks: number` | `ScoreLedger` | Yes |
| `apply_bulk_mark_deduction` | Apply percentage penalty to multiple enrollments | `enrollmentIds: string[], penaltyPercent: number, reason?: string, adminUserId: string` | `{ affectedCount, totalDeducted }` | Yes |

## Score Queries

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_score_ledger` | Get score records for an enrollment (filtered to active components including parent track) | `enrollmentId: string` | `ScoreLedger[]` | No |
| `get_student_score_summary` | Current track score summary (matches website, filtered to active components) | `studentId: string, enrollmentId?: string` | `{ total, byComponent }` | No |
| `list_students_with_marks` | Paginated students with marks | `filters: { trackConfigId?, programme?, section?, search?, page?, pageSize? }` | `{ items, total }` | No |
| `get_marks_hierarchy` | Get marks hierarchy with years, programmes, sections, tracks | `-` | `{ session, years, parentTracks, tracks }` | No |

### Score Query Behavior

Both `get_score_ledger` and `get_student_score_summary` filter entries to only include those matching **active components** from the enrollment's current track config (including parent track components). Old entries from changed criteria are automatically excluded.

## Mentor Evaluation

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_mentor_eval_scores` | Get mentor evaluation scores | `enrollmentId?: string, mentorId?: string` | `MentorEvalScore[]` | No |
| `submit_mentor_evaluation` | Submit mentor evaluation | `enrollmentId: string, fields: Array, overallComment?: string` | `MentorEvalScore` | Yes |

---

## API Routes (Mentor)

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/mentor/final-evaluation` | Submit final evaluation |