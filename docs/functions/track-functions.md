# Functions: Track Management

## Summary
Track CRUD, session config. Use when query involves track, config.

---

## Track CRUD

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `list_tracks` | List all tracks | `filters?: { trackType?, search? }` | `Track[]` | No |
| `get_track` | Get track by ID | `track_id: string` | `Track` | No |
| `get_track_by_code` | Get track by code | `code: string` | `Track` | No |
| `create_track` | Create new track | `trackData: { name, code, trackType, ... }` | `Track` | Yes |
| `update_track` | Update track definition | `track_id: string, fields` | `Track` | Yes |
| `delete_track` | Delete track definition | `track_id: string` | `void` | Yes |

## Session Config

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `get_track_config` | Get session config for track | `session_id: string, track_id: string` | `TrackSessionConfig` | No |
| `list_track_configs` | List configs for session | `session_id: string, filters?` | `TrackSessionConfig[]` | No |
| `copy_track_configs` | Copy track configs from one session to another | `actor, input: { sourceSessionId, targetSessionId, sourceConfigIds? }` | `{ copied: number, skipped: number, errors: string[] }` | Yes |
| `update_track_config` | Update session config | `config_id: string, fields` | `TrackSessionConfig` | Yes |

---

## API Routes (Admin)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/admin/tracks` | List all tracks |
| POST | `/api/admin/tracks` | Create track |
| PATCH | `/api/admin/tracks/[trackId]` | Update track |
| DELETE | `/api/admin/tracks/[trackId]` | Delete track |