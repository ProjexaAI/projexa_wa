# Schema: Announcements

## Summary
Announcements and notifications. All notifications (broadcasts, interaction events, low attendance alerts) are stored in the single `announcements` collection. Use this doc when query involves notification, announcement, alert, broadcast.

---

## announcements

Announcements to students/mentors. Also used for per-user interaction notifications (with `deliveryChannels: ["IN_APP"]` and single recipient in `recipientStatuses`).

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
  creatorRole: String,             // "ADMIN" | "MENTOR"
  recipientStatuses: [{            // embedded array — per-user tracking
    userId: ObjectId,
    status: String,                // "PENDING" | "SENT"
    sentAt: Date
  }],
  readBy: [ObjectId],              // users who have read this announcement
  readCount: Number,
  recipientCount: Number,
  status: String,                  // "SENT" | "PENDING"
  scheduledFor: Date,
  createdAt: Date
}
```
