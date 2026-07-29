# Functions: User Management

## Summary
User CRUD. Use when query involves user, student, mentor, faculty.

---

## User CRUD Functions

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_user_by_id` | Fetch user by ID | `user_id: string` | `User` | No |
| `get_user_by_email` | Fetch user by email | `email: string` | `User` | No |
| `list_users` | List users with filters | `role?: string, session?: string, page?: number, pageSize?: number, search?: string` | `{ items, total, page, pageSize }` | No |
| `list_students_hierarchical` | List students grouped by year/programme/section with mentor info | `search?: string` | `{ categories, sessionLabel, mentors }` | No |
| `create_user` | Create new user | `userData: { name, email, roles, ... }` | `User` | Yes |
| `update_user` | Update user fields | `user_id: string, fields: Partial<User>` | `User` | Yes |
| `delete_user` | Soft delete user | `user_id: string` | `void` | Yes |

## Bulk Sync (Projexa)

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `bulk_sync_students_from_projexa` | Sync students from Projexa records | `actor, input: { records: Array }` | `{ received, processed, created, updated, skipped, errors }` | Yes |
| `bulk_sync_mentors_from_projexa` | Sync mentors from Projexa records | `actor, input: { records: Array }` | `{ received, processed, created, updated, skipped, errors }` | Yes |
| `bulk_sync_students_from_projexa_db` | Sync students directly from Projexa database | `actor, input?: { sessionYear?, sessionSemester?, studentYears? }` | `{ received, processed, created, updated, skipped, errors }` | Yes |
| `bulk_sync_mentors_from_projexa_db` | Sync mentors directly from Projexa database | `actor` | `{ received, processed, created, updated, skipped, errors }` | Yes |

---

## API Routes (Admin)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/admin/users` | List all users |
| PATCH | `/api/admin/users/[userId]` | Update user |
| DELETE | `/api/admin/users/[userId]` | Delete user |