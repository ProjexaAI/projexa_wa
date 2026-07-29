# Functions: Notifications

## Summary
List notifications, mark read. Use when query involves notification, unread, mark read.

---

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_notifications` | List user notifications | `userId: string, filters?: { status?, type? }` | `Notification[]` | No |
| `get_unread_count` | Get unread notification count | `userId: string` | `number` | No |
| `mark_notification_read` | Mark notification as read | `notificationId: string` | `void` | Yes |

---

## API Routes (Shared)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/notifications` | List notifications |
| POST | `/api/notifications/[notificationId]/read` | Mark as read |