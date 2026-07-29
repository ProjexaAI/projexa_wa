# Schema: Notifications & Announcements

## Summary
In-app notifications and announcements. Use this doc when query involves notification, announcement, alert, broadcast.

---

## notifications

In-app notifications.

```js
{
  _id: ObjectId,
  userId: ObjectId,
  type: String,                    // "ANNOUNCEMENT" | "INTERACTION_SCHEDULED" | "INTERACTION_REMINDER" | "INTERACTION_RESCHEDULED" | "INTERACTION_COMPLETED" | "INTERACTION_SCORES_PUBLISHED"
  title: String,
  message: String,
  actionUrl: String,
  status: String,                  // "PENDING" | "SENT"
  readAt: Date,
  scheduledFor: Date
}
```

**Key index:** `{ userId: 1, status: 1 }`

---

## announcements

Announcements to students/mentors.

```js
{
  _id: ObjectId,
  title: String,
  message: String,
  audience: String,                // "STUDENTS" | "MENTORS" | "BOTH"
  deliveryChannels: [String],      // "EMAIL" | "IN_APP"
  trackScope: String,              // "ALL_TRACKS" | "SELECTED_TRACKS" | "UNASSIGNED_STUDENTS"
  targetTrackNames: [String],
  creatorName: String,
  recipientCount: Number,
  readCount: Number,
  createdAt: Date
}
```
