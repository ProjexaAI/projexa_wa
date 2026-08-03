# Schema: Mentor

## Summary
Mentor assignments, interactions, progress tracking. Use this doc when query involves mentor, interaction, assignment, progress, meeting.

---

## enrollmentmentorassignments

Mentor-to-student assignments.

```js
{
  _id: ObjectId,
  sessionId: ObjectId,             // ref: "AcademicYear"
  enrollmentId: ObjectId,          // ref: "StudentTrackEnrollment"
  studentId: ObjectId,
  mentorId: ObjectId,
  assignedByUserId: ObjectId,      // ref: "User"
  assignedAt: Date,
  isActive: Boolean,
  releasedAt: Date,
  releaseReason: String
}
```

**Key index:** `{ enrollmentId: 1, isActive: 1 }` — unique partial (isActive: true)

---

## mentorstudentinteractions

Individual mentor-student interactions (meetings, calls).

```js
{
  _id: ObjectId,
  sessionId: ObjectId,             // ref: "AcademicYear"
  mentorInteractionSessionId: ObjectId,  // ref: "MentorInteractionSession"
  enrollmentId: ObjectId,
  assignmentId: ObjectId,          // ref: "EnrollmentMentorAssignment"
  trackSessionConfigId: ObjectId,
  interactionTemplateId: ObjectId,
  studentId: ObjectId,
  mentorId: ObjectId,
  interactionNumber: Number,
  title: String,
  summary: String,
  notes: String,
  nextAction: String,
  scheduledAt: Date,
  meetingTitle: String,
  meetingLink: String,
  meetingMode: String,             // "ONLINE" | "OFFLINE"
  durationMinutes: Number,
  meetingNotes: String,
  windowStartsAt: Date,
  windowEndsAt: Date,
  questionScores: [{               // embedded — per-question scoring
    key: String,
    prompt: String,
    questionType: String,          // "RADIO_SCORE" | "NUMERIC_SCORE" | "TEXT_FEEDBACK"
    maxMarks: Number,
    displayOrder: Number,
    scoreAwarded: Number,
    remarks: String
  }],
  startedAt: Date,
  endedAt: Date,
  status: String,                  // "PENDING" | "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED"
  scoreAwarded: Number,
  maxScore: Number,
  finalizedAt: Date,
  finalizedByMentorId: ObjectId
}
```

**Key index:** `{ enrollmentId: 1, interactionNumber: 1 }`

---

## mentorinteractionsessions

Scheduled mentor interaction sessions (group sessions).

```js
{
  _id: ObjectId,
  mentorId: ObjectId,
  title: String,
  scheduledAt: Date,
  meetingLink: String,
  overallSummary: String,
  status: String                   // "SCHEDULED" | "ONGOING" | "COMPLETED"
}
```

---

## studentprogresses

Student progress tracking (interaction completion).

```js
{
  _id: ObjectId,
  sessionId: ObjectId,             // ref: "AcademicYear"
  studentId: ObjectId,
  mentorId: ObjectId,
  assignmentId: ObjectId,
  interactions: [{
    interactionNumber: Number,
    dueDate: Date,
    scheduledDateTime: Date,
    completed: Boolean,
    completedAt: Date
  }]
}
```

**Key index:** `{ assignmentId: 1 }` — unique
