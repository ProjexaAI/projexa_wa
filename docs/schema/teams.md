# Schema: Teams

## Summary
Teams and team invitations for group tracks. Use this doc when query involves team, group, invite, join.

---

## teams

Teams for group tracks.

```js
{
  _id: ObjectId,
  name: String,
  inviteCode: String,
  sessionId: ObjectId,
  trackSessionConfigId: ObjectId,
  leaderId: ObjectId,              // ref: "User"
  memberIds: [ObjectId],           // ref: "User"
  source: String,                  // "ADMIN_CREATED" | "STUDENT_CREATED"
  status: String                   // "FORMING" | "SUBMITTED"
}
```

**Key index:** `{ sessionId: 1, inviteCode: 1 }`

---

## teaminvitations

Team invitations.

```js
{
  _id: ObjectId,
  teamId: ObjectId,
  inviterId: ObjectId,
  inviteeId: ObjectId,
  status: String,                  // "PENDING" | "ACCEPTED" | "DECLINED"
  respondedAt: Date
}
```
