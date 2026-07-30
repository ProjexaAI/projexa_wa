# Functions: Teams

## Summary
Create, join, invite, respond to team invitations. Use when query involves team, group, invite, join, code.

---

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_teams` | List teams for session | `sessionId?: string, trackSessionConfigId?: string, memberId?: string` | `Team[]` | No |
| `get_team` | Get team details | `teamId: string` | `Team` | No |
| `create_team` | Create new team | `teamData: { name, leaderId, sessionId, trackSessionConfigId }` | `Team` | Yes |
| `join_team` | Join via invite code | `inviteCode: string, studentId: string` | `Team` | Yes |
| `invite_to_team` | Send invitation | `teamId: string, inviteeId: string` | `Invitation` | Yes |
| `respond_to_invitation` | Accept/decline | `invitationId: string, response: "ACCEPTED"\|"DECLINED"` | `Invitation` | Yes |
| `leave_team` | Leave team | `teamId: string, studentId: string` | `void` | Yes |
| `remove_from_team` | Remove member (leader) | `teamId: string, memberId: string` | `void` | Yes |

---

## API Routes (Student)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/student/teams/[...action]` | Get team info |
| POST | `/api/student/teams/[...action]` | Team actions (create/join/leave/remove) |