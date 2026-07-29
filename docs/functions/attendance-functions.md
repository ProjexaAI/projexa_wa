# Functions: Attendance

## Summary
Mark attendance, view records, view stats. Use when query involves attendance, mark, present, absent.

---

## Mark Attendance

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `mark_attendance` | Mark single student attendance | `enrollmentId: string, dateKey: string, status: "PRESENT"\|"ABSENT", session: "MORNING"\|"EVENING"` | `Attendance` | Yes |
| `mark_attendance_as_admin` | Admin direct attendance marking | `studentId: string, dateKey: string, status: string, session: string` | `Attendance` | Yes |
| `mark_attendance_as_admin_bulk` | Bulk mark attendance for multiple students | `entries: Array<{ enrollmentId, status, dateKey?, attendanceSession? }>` | `{ marked: number }` | Yes |

## Export & Import

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `export_attendance_report` | Export attendance report as XLSX/CSV/PDF | `trackConfigId?, parentTrackId?, mentorId?, sessionDateKey?, format: "xlsx"\|"csv"\|"pdf"`, `filters?` | `{ buffer, fileName, contentType }` | No |
| `preview_attendance_import` | Preview attendance import file before executing | `fileBuffer: ArrayBuffer, fileName: string, sheetName: string, trackConfigId?` | `{ columns, previewRows, validation }` | No |
| `execute_attendance_import` | Execute attendance import from spreadsheet | `fileBuffer: ArrayBuffer, fileName: string, sheetName: string, trackConfigId: string, mode: string, adminUserId: string` | `{ totalRecords, imported, updated, skipped, failed, errors }` | Yes |

## View Attendance

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_student_attendance` | Get student's attendance records | `studentId: string, session?: string, dateRange?: { start, end }` | `Attendance[]` | No |
| `get_session_attendance` | Get all attendance for session | `trackSessionConfigId: string, dateKey: string, session: string` | `Attendance[]` | No |
| `get_attendance_stats` | Get attendance statistics | `enrollmentId?: string, trackSessionConfigId?: string` | `AttendanceStats` | No |
| `get_attendance_calendar` | Get attendance calendar view | `studentId: string, month: number, year: number` | `CalendarDay[]` | No |

---

## API Routes (Student)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/student/attendance` | Get attendance data |

## API Routes (Mentor)

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/mentor/attendance` | Record attendance |
| GET | `/api/mentor/attendance/calendar` | Get attendance calendar |