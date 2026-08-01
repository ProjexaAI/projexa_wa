# Functions: Onboarding

## Summary
Submit documents, intake forms, review submissions. Use when query involves onboarding, submit, document, intake, review.

---

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_onboarding_status` | Get onboarding status for enrollment | `enrollmentId: string` | `OnboardingStatus` | No |
| `list_onboarding_queue` | List admin onboarding review queue | `adminUserId: string, filters?: { search?, trackLabel?, section?, yearLevel? }` | `AdminOnboardingQueueData` | No |
| `get_pending_onboarding_review_metrics` | Get pending review counts (intake + documents) | `adminUserId: string` | `{ pendingSubmissionCount, pendingDocumentCount, pendingStudentCount }` | No |
| `list_additional_doc_queue` | List mentor's additional document review queue | `mentorUserId: string, filters?: { search?, trackLabel?, section?, yearLevel? }` | `MentorDocumentReviewQueueData` | No |
| `submit_document` | Submit document files | `enrollmentId: string, templateId: string, files: Array` | `DocumentSubmission` | Yes |
| `submit_intake_form` | Submit intake form responses | `enrollmentId: string, templateId: string, responses: Object` | `IntakeSubmission` | Yes |
| `review_submission` | Review intake submission | `submissionId: string, decision: "APPROVED"\|"REJECTED", comment?: string` | `Submission` | Yes |
| `review_document_submission` | Review document submission (admin) | `adminUserId: string, submissionId: string, decision: "APPROVED"\|"REJECTED", reviewComment?, awardedMarks?, rejectionItems?` | `DocumentSubmission` | Yes |
| `review_document_as_mentor` | Review document submission (mentor) | `mentorUserId: string, submissionId: string, decision: "APPROVED"\|"REJECTED", reviewComment?, awardedMarks?, rejectionItems?` | `DocumentSubmission` | Yes |
| `get_submissions` | List submissions | `enrollmentId?: string, filters?: { status?, kind? }` | `Submission[]` | No |
| `submit_document_upload` | Submit a previously uploaded document (from WhatsApp) to a track onboarding | `studentId: string, documentTemplateId: string, fileUrl: string, objectKey: string, fileName: string, fileSizeBytes: int, contentType: string` | `DocumentSubmission` | Yes |

---

## API Routes (Student)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/student/tracks/onboarding` | Get onboarding status |
| POST | `/api/student/tracks/onboarding/initial` | Submit initial onboarding |
| POST | `/api/student/tracks/onboarding/intake` | Submit intake form |
| POST | `/api/student/tracks/onboarding/documents` | Submit document |