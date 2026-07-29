# Schema: Mentor

## Summary
Mentor assignments, interactions, progress tracking. Use this doc when query involves mentor, interaction, assignment, progress, meeting.

---

## enrollmentmentorassignments

Mentor-to-student assignments.

```js
{
  _id: ObjectId,
  enrollmentId: ObjectId,          // ref: "StudentTrackEnrollment"
  studentId: ObjectId,
  mentorId: ObjectId,
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
  enrollmentId: ObjectId,
  studentId: ObjectId,
  mentorId: ObjectId,
  interactionNumber: Number,
  title: String,
  summary: String,
  nextAction: String,
  scheduledAt: Date,
  meetingMode: String,             // "ONLINE" | "OFFLINE"
  durationMinutes: Number,
  status: String,                  // "PENDING" | "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED"
  scoreAwarded: Number,
  maxScore: Number
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
  studentId: ObjectId,
  mentorId: ObjectId,
  assignmentId: ObjectId,
  interactions: [{
    interactionNumber: Number,
    dueDate: Date,
    completed: Boolean,
    completedAt: Date
  }]
}
```

**Key index:** `{ assignmentId: 1 }` — unique
