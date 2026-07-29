# Schema: Core Entities

## Summary
Core entities: users, academic years, tracks, track session configs, and enrollments. Use this doc when query involves users, tracks, sessions, or enrollment status.

---

## users

User accounts (students, mentors, admins).

```js
{
  _id: ObjectId,
  name: String,
  email: String,
  roles: [String],                 // "ADMIN" | "PLACEMENT_COORDINATOR" | "MENTOR" | "STUDENT"
  rollNumber: String,
  mobileNumber: String,
  programme: String,
  section: String,
  isActive: Boolean,
  isDefaulter: Boolean
}
```

---

## academicyears

Academic session/year definitions.

```js
{
  _id: ObjectId,
  name: String,
  sessionYear: Number,
  sessionTerm: String,             // "ODD" | "EVEN"
  startDate: Date,
  endDate: Date,
  isActive: Boolean,
  isArchived: Boolean
}
```

---

## tracks

Track definitions (courses/programs).

```js
{
  _id: ObjectId,
  name: String,
  code: String,
  trackType: String,               // "GROUP" | "OPTION"
  description: String
}
```

---

## tracksessionconfigs

Links a track to an academic session with settings.

```js
{
  _id: ObjectId,
  sessionId: ObjectId,             // ref: "AcademicYear"
  trackId: ObjectId,               // ref: "Track"
  isEnabled: Boolean,
  mode: String,                    // "INDIVIDUAL" | "TEAM"
  minTeamSize: Number,
  maxTeamSize: Number,
  maxTotalMarks: Number
}
```

**Key index:** `{ sessionId: 1, trackId: 1 }` — unique

---

## studenttrackenrollments

Student's enrollment in a track session.

```js
{
  _id: ObjectId,
  studentId: ObjectId,             // ref: "User"
  sessionId: ObjectId,             // ref: "AcademicYear"
  trackSessionConfigId: ObjectId,  // ref: "TrackSessionConfig"
  status: String,                  // "PENDING_ONBOARDING" | "ENROLLED" | "ACTIVE" | "INACTIVE" | "SWITCHED_OUT" | "COMPLETED"
  section: String,
  mentorId: ObjectId,              // ref: "User"
  isOnboardingSubmitted: Boolean,
  startedAt: Date,
  endedAt: Date
}
```
