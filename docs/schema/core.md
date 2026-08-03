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
  studentYear: String,
  profilePicture: String,          // CDN URL to profile photo (may be null)
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
  academicYears: [{                // embedded — year level config
    level: Number,                 // 1-4
    label: String,
    isEnabled: Boolean
  }],
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
  allowMentorSubTracks: Boolean,
  parentTrackId: ObjectId,         // ref: "Track" (self-ref for sub-tracks)
  sortOrder: Number,
  description: String,
  program: {                       // embedded — course content
    overview: String,
    learningOutcomes: [String],
    deliverables: [String],
    days: [{dayNumber: Number, title: String, description: String, objectives: [String]}]
  }
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
  maxTeamsPerMentor: Number,
  teamSourceMode: String,          // "PREDEFINED_ONLY" | "SELF_CREATE_ONLY" | "BOTH"
  allowTrackChangeRequest: Boolean,
  eligibilityRules: [{             // embedded — who can enroll
    yearLevel: Number,
    programmeCode: String,
    sectionCode: String,
    isActive: Boolean
  }],
  documentTemplates: [{            // embedded — required documents
    _id: ObjectId,
    code: String,
    title: String,
    isMandatory: Boolean,
    appliesTo: String,             // "STUDENT" | "TEAM" | "BOTH"
    submissionPhase: String,       // "ONBOARDING" | "ADDITIONAL"
    requiresApproval: Boolean,
    submissionMode: String,        // "SINGLE" | "MULTIPLE"
    maxFiles: Number,
    allowedFileTypes: [String],
    isActive: Boolean
  }],
  intakeTemplate: {                // embedded — intake form (nullable)
    _id: ObjectId,
    title: String,
    isActive: Boolean,
    fields: [{key: String, label: String, type: String, required: Boolean}]
  },
  assessmentComponents: [{         // embedded — grading criteria
    _id: ObjectId,
    code: String,
    title: String,
    type: String,                  // "DOCUMENT" | "INTERACTION" | "FINAL_EVALUATION" | "ATTENDANCE" | "MENTOR_EVALUATION" | "FINAL_YEAR_MENTOR_EVALUATION" | "EMAIL" | "MANUAL"
    maxMarks: Number,
    yearMarks: Map,                // per-year marks override
    displayOrder: Number,
    isActive: Boolean,
    yearLevels: [Number],
    rolloverPolicy: String,        // "NONE" | "PERCENTAGE_TO_CURRENT_COMPONENT"
    mentorEvaluationFields: [{label: String, maxMarks: Number}]
  }],
  rubricTemplates: [{              // embedded — rubric grading
    _id: ObjectId,
    version: Number,
    totalMarks: Number,
    isActive: Boolean
  }],
  interactionTemplates: [{         // embedded — interaction sessions
    _id: ObjectId,
    code: String,
    interactionNumber: Number,
    title: String,
    description: String,
    startsAt: Date,
    endsAt: Date,
    totalMarks: Number,
    isActive: Boolean,
    questions: [{key: String, prompt: String, questionType: String, maxMarks: Number, displayOrder: Number}]
  }],
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
  isActive: Boolean,
  mentorId: ObjectId,              // ref: "User"
  isOnboardingSubmitted: Boolean,
  onboardingSubmittedAt: Date,
  startedAt: Date,
  activatedAt: Date,
  endedAt: Date,
  endedReason: String,
  switchedFromEnrollmentId: ObjectId,  // ref: "StudentTrackEnrollment" (self-ref)
  switchRequestId: ObjectId        // ref: "TrackSwitchRequest"
}
```
