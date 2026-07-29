# Enum Constants Reference

## User Roles
```
ADMIN, PLACEMENT_COORDINATOR, MENTOR, STUDENT
```

## Academic Year
```
Session Terms: ODD, EVEN
```

## Announcement
```
Audiences:       STUDENTS, MENTORS, BOTH
Track Scopes:    ALL_TRACKS, SELECTED_TRACKS, UNASSIGNED_STUDENTS
Creator Roles:   ADMIN, MENTOR
Recipient Roles: STUDENT, MENTOR
Delivery:        EMAIL, IN_APP
```

## Track
```
Track Types:     GROUP, OPTION
Modes:           INDIVIDUAL, TEAM
Team Source:      PREDEFINED_ONLY, SELF_CREATE_ONLY, BOTH
```

## Enrollment Status
```
PENDING_ONBOARDING, ENROLLED, ACTIVE, INACTIVE, SWITCHED_OUT, COMPLETED
```

## Track Switch Request
```
Status:        PENDING, APPROVED, REJECTED, CANCELLED
Decisions:     SWITCH_ENROLLMENT, DELETE_ENROLLMENT, REJECT_REQUEST
```

## Assessment Component Types
```
DOCUMENT, INTERACTION, FINAL_EVALUATION, ATTENDANCE, MENTOR_EVALUATION,
FINAL_YEAR_MENTOR_EVALUATION, EMAIL, MANUAL
```

## Score Component Types
```
INTAKE, DOCUMENT, INTERACTION, RUBRIC, ATTENDANCE, MENTOR_EVALUATION,
FINAL_YEAR_MENTOR_EVALUATION, EMAIL, MANUAL
```

## Assessment Rollover Policies
```
NONE, PERCENTAGE_TO_CURRENT_COMPONENT
```

## Assessment Field Types
```
SHORT_TEXT, LONG_TEXT, SINGLE_SELECT, YES_NO, NUMERIC_SCORE
```

## Intake Field Types
```
SHORT_TEXT, LONG_TEXT, NUMBER, DATE, SINGLE_SELECT, MULTI_SELECT,
CHECKBOX, FILE
```

## Validation Types
```
NONE, EMAIL, INTERNAL_EMAIL, PHONE, URL, ROLL_NUMBER, GST_NUMBER, ALPHANUMERIC
```

## Interaction
```
Statuses:        PENDING, SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED
Session Status:  SCHEDULED, ONGOING, COMPLETED
Student Status:  SCHEDULED, ONGOING, EVALUATED, MISSED
Meeting Modes:   ONLINE, OFFLINE
Question Types:  RADIO_SCORE, NUMERIC_SCORE, TEXT_FEEDBACK
```

## Attendance
```
Sessions:   MORNING, EVENING
Sources:    MANUAL, QR_SCAN
Confidence: HIGH, REVIEW, SUSPICIOUS
Status:     PRESENT, ABSENT
```

## Evaluation Event
```
Status:    SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED
Modes:     ONLINE, OFFLINE
Participant Status: SCHEDULED, COMPLETED, EXEMPT, CANCELLED
```

## Document/Intake Submission
```
Submission Kinds: DOCUMENT, INTAKE
Status:          DRAFT, SUBMITTED, APPROVED, REJECTED, SWITCHED_OUT
Reviewer Roles:  ADMIN, MENTOR
```

## Notification
```
Types:   ANNOUNCEMENT, INTERACTION_SCHEDULED, INTERACTION_REMINDER,
         INTERACTION_RESCHEDULED, INTERACTION_COMPLETED,
         INTERACTION_SCORES_PUBLISHED
Status:  PENDING, SENT
```

## Support Ticket
```
Types:    SUPPORT, MEETING
Categories: MENTORSHIP, TRACK, ONBOARDING, EVALUATION, DOCUMENTS,
            TECHNICAL, MEETING, OTHER
Priority: LOW, MEDIUM, HIGH, URGENT
Channels: EMAIL, PHONE, CHAT, MEETING
Status:   OPEN, IN_PROGRESS, RESOLVED, ESCALATED, CLOSED
Actor:    STUDENT, MENTOR, ADMIN, SYSTEM
```

## Team
```
Source: ADMIN_CREATED, STUDENT_CREATED
Status: FORMING, SUBMITTED
```

## Team Invitation
```
Status: PENDING, ACCEPTED, DECLINED
```

## Admin Audit Entity Types
```
USER, ACADEMIC_YEAR, SESSION_ACADEMIC_YEAR, USER_IMPORT, MENTOR_ASSIGNMENT
```

## External Mentor Verification
```
Status: NOT_SENT, PENDING, VERIFIED_YES, VERIFIED_NO
```

## Email Assessment Request
```
Status: NOT_SENT, PENDING, SUBMITTED
```

## Placement Settings
```
Year Keys: 1st, 2nd, 3rd, 4th
```

## Personal Email OTP
```
Purpose: ONBOARDING_PERSONAL_EMAIL
```

## Track Session Config - Document Template
```
Applies To:        STUDENT, TEAM, BOTH
Submission Phases: ONBOARDING, ADDITIONAL
Submission Modes:  SINGLE, MULTIPLE
Upload Owner:      PER_STUDENT, TEAM_LEADER_ONLY
Document Eval:     NONE, CERTIFICATION_SCORE
```

## Track Session Config - Mentor Evaluation
```
Field Owner: ADMIN, MENTOR
Eval Status: OPEN, LOCKED
```

## Track Session Config - Team
```
Modes:            INDIVIDUAL, TEAM
Team Source Mode: PREDEFINED_ONLY, SELF_CREATE_ONLY, BOTH
```
