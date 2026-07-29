# Functions: Auth

## Summary
Login, session management, profile retrieval. Use when query involves login, auth, token, session.

---

| Function | Description | Params | Returns | Write? |
|----------|-------------|--------|---------|--------|
| `login` | Authenticate user with email/password | `email: string, password: string` | `{ token, user }` | No |
| `get_current_user` | Get logged-in user profile from JWT | `token: string` | `User` | No |
| `refresh_token` | Refresh JWT token before expiry | `token: string` | `{ token }` | No |

---

## API Routes

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/auth/projexa/login` | Initiates Projexa OAuth login flow |
| GET | `/api/auth/projexa/callback` | OAuth callback, exchanges code for session |
| GET | `/api/auth/me` | Returns current session user profile |
| PATCH | `/api/auth/me` | Updates current user profile |
| GET/POST | `/api/auth/logout` | Clears auth cookies |
| GET | `/api/auth/active-role` | Gets active role for current user |
| PUT | `/api/auth/active-role` | Switches active role |
