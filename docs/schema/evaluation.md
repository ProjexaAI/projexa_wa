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
  componentRefId: String,
  assessmentComponentId: ObjectId,
  assessmentComponentCode: String,
  assessmentComponentTitle: String,
  assessmentComponentType: String, // matches AssessmentComponentType enum
  marksAwarded: Number,
  maxMarks: Number,
  recordedByUserId: ObjectId,      // ref: "User"
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
  sessionId: ObjectId,             // ref: "AcademicYear"
  enrollmentId: ObjectId,
  studentId: ObjectId,
  trackSessionConfigId: ObjectId,
  assessmentComponentId: ObjectId,
  assessmentComponentCode: String,
  assessmentComponentTitle: String,
  mentorId: ObjectId,
  fields: [{                       // embedded — per-field scores
    key: String,
    label: String,
    maxMarks: Number,
    marksAwarded: Number,
    remarks: String
  }],
  overallComment: String,
  totalMarksAwarded: Number,
  totalMaxMarks: Number,
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
  assessmentComponentId: ObjectId,
  assessmentComponentCode: String,
  assessmentComponentTitle: String,
  title: String,
  instructions: String,
  mode: String,                    // "ONLINE" | "OFFLINE"
  venue: String,
  meetingLink: String,
  scheduledStartAt: Date,
  scheduledEndAt: Date,
  yearLevel: Number,
  evaluatorIds: [ObjectId],        // ref: "User"
  status: String,                  // "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED"
  participants: [{                  // embedded — per-student tracking
    enrollmentId: ObjectId,
    studentId: ObjectId,
    status: String,                // "SCHEDULED" | "COMPLETED" | "EXEMPT" | "CANCELLED"
    scoreAwarded: Number,
    maxScore: Number,
    remarks: String
  }]
}
```
