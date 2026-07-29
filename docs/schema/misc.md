# Schema: Miscellaneous

## Summary
Placement settings, external verification. Use this doc when query involves placement, external verification.

---

## placementsettings

Global placement settings.

```js
{
  _id: ObjectId,
  key: String,
  enabledYears: [{
    yearKey: String,               // "1st" | "2nd" | "3rd" | "4th"
    label: String,
    isEnabled: Boolean
  }]
}
```

---

## externalmentorverifications

External mentor verification for email assessments.

```js
{
  _id: ObjectId,
  enrollmentId: ObjectId,
  studentId: ObjectId,
  mentorEmail: String,
  mentorName: String,
  organizationName: String,
  studentName: String,
  trackName: String,
  status: String,                  // "NOT_SENT" | "PENDING" | "VERIFIED_YES" | "VERIFIED_NO"
  respondedAt: Date
}
```

---

## emailassessmentrequests

Email-based assessment requests.

```js
{
  _id: ObjectId,
  enrollmentId: ObjectId,
  studentId: ObjectId,
  recipientEmail: String,
  recipientName: String,
  studentName: String,
  trackName: String,
  assessmentComponentTitle: String,
  assessmentComponentMaxMarks: Number,
  status: String,                  // "NOT_SENT" | "PENDING" | "SUBMITTED"
  scoreAwarded: Number,
  submittedAt: Date
}
```
