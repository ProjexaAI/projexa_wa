# Functions: Admin

## Summary
Academic year management, track switch requests. Use when query involves academic year, session, track switch.

---

## Academic Year Management

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_academic_years` | List academic years | `page?, pageSize?` | `{ items, total }` | No |
| `create_academic_year` | Create academic year | `yearData: { name, sessionYear, sessionTerm }` | `AcademicYear` | Yes |
| `update_academic_year` | Update academic year | `yearId: string, fields` | `AcademicYear` | Yes |
| `get_current_session` | Get active session | `-` | `AcademicYear` | No |
| `set_current_session` | Set active session | `yearId: string` | `void` | Yes |

## Track Switch Requests

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_switch_requests` | List track switch requests | `filters, page?, pageSize?` | `{ items, total }` | No |
| `get_switch_request_details` | Get request details | `requestId: string` | `SwitchRequest` | No |
| `review_switch_request` | Approve/reject request | `requestId: string, decision: string, comment?: string` | `SwitchRequest` | Yes |

## Data Export

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `plan_onboarding_documents_export` | Plan onboarding documents ZIP export | `configIds: string[]` | `OnboardingDocumentsExportPlan` | No |
| `export_profile_pdf` | Export single student profile as HTML/PDF | `studentId: string, download?: boolean` | `HTML content` | No |
| `export_bulk_profile_pdfs` | Export bulk student profiles as ZIP | `year?, program?, section?` | `ZIP archive` | No |

---

## API Routes

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/admin/years` | List academic years |
| POST | `/api/admin/years` | Create academic year |
| PUT | `/api/admin/years/active` | Set active session |
| PATCH | `/api/admin/years/[yearId]` | Update academic year |
| GET | `/api/admin/track-switch-requests` | List switch requests |
| PATCH | `/api/admin/track-switch-requests/[requestId]` | Review request |