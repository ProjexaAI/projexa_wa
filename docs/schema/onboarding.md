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
  sessionId: ObjectId,             // ref: "AcademicYear"
  yearLevel: Number,
  enrollmentId: ObjectId,
  trackSessionConfigId: ObjectId,
  documentTemplateId: ObjectId,
  attemptNumber: Number,
  files: [{                        // embedded — uploaded files
    fileName: String,
    fileUrl: String,
    objectKey: String,
    fileSizeBytes: Number,
    contentType: String
  }],
  status: String,                  // "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED" | "SWITCHED_OUT"
  submittedAt: Date,
  reviewedByAdminId: ObjectId,
  reviewedByUserId: ObjectId,
  reviewedByRole: String,          // "ADMIN" | "MENTOR"
  reviewedAt: Date,
  reviewComment: String,
  awardedMarks: Number,
  obtainedMarks: Number,
  totalMarks: Number,
  passingMarks: Number,
  percentage: Number,
  result: String,                  // "PASS" | "FAIL"
  rejectionItems: [{               // embedded — per-file rejection
    fileIndex: Number,
    reason: String
  }]
}
```

**Key index:** `{ enrollmentId: 1, documentTemplateId: 1, attemptNumber: 1 }` — unique

### Intake Submissions (`submissionKind: "INTAKE"`)

```js
{
  _id: ObjectId,
  submissionKind: String,          // "INTAKE" (immutable)
  studentId: ObjectId,
  sessionId: ObjectId,             // ref: "AcademicYear"
  yearLevel: Number,
  enrollmentId: ObjectId,
  trackSessionConfigId: ObjectId,
  intakeTemplateId: ObjectId,
  attemptNumber: Number,
  responseData: Object,            // free-form key-value intake answers
  status: String,                  // "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED"
  submittedAt: Date,
  reviewedByAdminId: ObjectId,
  reviewedAt: Date,
  reviewComment: String,
  rejectionItems: [{               // embedded — per-field rejection
    fieldKey: String,
    reason: String
  }]
}
```
