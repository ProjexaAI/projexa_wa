# Schema: Onboarding

## Summary
Document and intake form submissions for track onboarding. Use this doc when query involves onboarding, submit docs, intake form, document review.

---

## trackonboardingsubmissions

Document and intake submissions (discriminated by `submissionKind`).

### Document Submissions (`submissionKind: "DOCUMENT"`)

```js
{
  _id: ObjectId,
  submissionKind: String,          // "DOCUMENT" (immutable)
  studentId: ObjectId,
  enrollmentId: ObjectId,
  trackSessionConfigId: ObjectId,
  attemptNumber: Number,
  status: String,                  // "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED" | "SWITCHED_OUT"
  submittedAt: Date,
  reviewedAt: Date,
  reviewComment: String,
  awardedMarks: Number,
  totalMarks: Number,
  passingMarks: Number,
  percentage: Number,
  result: String                   // "PASS" | "FAIL"
}
```

**Key index:** `{ enrollmentId: 1, documentTemplateId: 1, attemptNumber: 1 }` — unique

### Intake Submissions (`submissionKind: "INTAKE"`)

```js
{
  _id: ObjectId,
  submissionKind: String,          // "INTAKE" (immutable)
  studentId: ObjectId,
  enrollmentId: ObjectId,
  attemptNumber: Number,
  status: String,                  // "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED"
  submittedAt: Date,
  reviewedAt: Date,
  reviewComment: String
}
```
