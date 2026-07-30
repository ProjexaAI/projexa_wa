# Functions: Announcements

## Summary
Create, list, read announcements. Use when query involves announcement, broadcast.

---

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_announcements` | List announcements for user's role | `userId?: string, userRole?: string, page?: int, pageSize?: int` | `Announcement[]` | No |
| `get_announcement` | Get announcement detail | `announcementId: string` | `Announcement` | No |
| `create_announcement` | Create announcement | `announcementData: { title, message, audience, trackScope, ... }` | `Announcement` | Yes |
| `mark_announcement_read` | Mark as read | `announcementId: string, userId: string` | `void` | Yes |

**Students:** Pass your `userRole: "student"` to see relevant announcements. The system filters by your role automatically.

---

## API Routes (Shared)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/announcements` | List announcements |
| GET | `/api/announcements/[announcementId]` | Get detail |
| POST | `/api/announcements/[announcementId]/read` | Mark as read |