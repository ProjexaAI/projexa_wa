# Schema: Evaluation & Scoring

## Summary
Scoring, evaluation events, and grade tracking. Use this doc when query involves scores, marks, evaluation, grading, rubrics.

---

## enrollmentscoreledgers

Score ledger for enrollments (immutable audit trail of marks).

```js
{
  _id: ObjectId,
  enrollmentId: ObjectId,          // ref: "StudentTrackEnrollment"
  componentType: String,           // "INTAKE" | "DOCUMENT" | "INTERACTION" | "RUBRIC" | "ATTENDANCE" | "MENTOR_EVALUATION" | "EMAIL" | "MANUAL"
  assessmentComponentTitle: String,
  marksAwarded: Number,
  maxMarks: Number,
  recordedAt: Date
}
```

**Key index:** `{ enrollmentId: 1, recordedAt: -1 }`

---

## mentorevaluationscores

Mentor evaluation scores (per-field scoring).

```js
{
  _id: ObjectId,
  enrollmentId: ObjectId,
  studentId: ObjectId,
  mentorId: ObjectId,
  assessmentComponentTitle: String,
  totalMarksAwarded: Number,
  totalMaxMarks: Number,
  overallComment: String,
  submittedAt: Date
}
```

---

## trackevaluationevents

Scheduled evaluation sessions.

```js
{
  _id: ObjectId,
  sessionId: ObjectId,
  trackSessionConfigId: ObjectId,
  assessmentComponentTitle: String,
  title: String,
  mode: String,                    // "ONLINE" | "OFFLINE"
  venue: String,
  meetingLink: String,
  scheduledStartAt: Date,
  scheduledEndAt: Date,
  status: String                   // "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED"
}
```
