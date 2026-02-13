# API Reference

Configuration variables and CLI options for Canvas to Outlook Task Sync.

---

## Environment Variables

### Canvas

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CANVAS_BASE_URL` | Yes | — | Canvas instance URL (e.g., `https://school.instructure.com`). Must use HTTPS. |
| `CANVAS_ACCESS_TOKEN` | Yes | — | Personal Access Token from Canvas Settings. Never log or commit. |

### Microsoft

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MICROSOFT_CLIENT_ID` | Yes | — | Azure AD application (client) ID. |
| `MICROSOFT_TENANT_ID` | Yes | — | Azure AD tenant ID. Use `common` for multi-tenant/personal. |
| `MICROSOFT_REDIRECT_URI` | No | `http://localhost:8400` | OAuth redirect URI. Must match Azure app registration. |
| `MICROSOFT_TOKEN_CACHE` | No | `data/token_cache.json` | Path to MSAL token cache file. |

### Sync

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SYNC_TASK_LIST_NAME` | No | `Canvas Assignments` | Name of the Outlook task list to sync to. |
| `SYNC_DRY_RUN` | No | `false` | Set to `true` to preview changes without applying. |
| `SYNC_MAX_RETRIES` | No | `3` | Max retries for transient API failures. |
| `SYNC_RETRY_DELAY` | No | `1.0` | Base delay in seconds between retries. |

### Storage

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STORAGE_DATABASE_PATH` | No | `data/sync_state.db` | Path to SQLite state database. |

### Logging

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOG_LEVEL` | No | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

---

## CLI Options

### Main Command

```bash
python -m src.main [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--dry-run` | — | Preview changes without creating/updating tasks. |
| `--verbose` | `-v` | Enable verbose (DEBUG) logging. |
| `--env PATH` | — | Path to `.env` file. Default: `.env` in current directory. |
| `--reset-auth` | — | Clear cached Microsoft tokens and force re-authentication. |
| `--status` | — | Show sync status (counts) and exit. No sync performed. |

### Examples

```bash
# Full sync
python -m src.main

# Preview only
python -m src.main --dry-run

# Debug output
python -m src.main --verbose

# Use custom env file
python -m src.main --env /path/to/.env

# Clear Microsoft auth and re-login
python -m src.main --reset-auth

# Check status only
python -m src.main --status
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Configuration error, auth failure, or sync errors |
| 130 | Interrupted by user (Ctrl+C) |

---

## Canvas API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/courses?enrollment_state=active` | Fetch active courses. |
| `GET /api/v1/courses/{id}/assignments?include[]=submission` | Fetch assignments with submission status. |
| `GET /api/v1/courses/{id}/assignments/{id}/submissions/self` | Fetch single submission (optional, for targeted refresh). |

---

## Microsoft Graph API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /me/todo/lists` | List task lists. |
| `POST /me/todo/lists` | Create task list (if "Canvas Assignments" missing). |
| `GET /me/todo/lists/{id}/tasks` | List tasks. |
| `POST /me/todo/lists/{id}/tasks` | Create task. |
| `GET /me/todo/lists/{id}/tasks/{id}` | Get single task. |
| `PATCH /me/todo/lists/{id}/tasks/{id}` | Update task. |
| `DELETE /me/todo/lists/{id}/tasks/{id}` | Delete task (not used by sync; archive preferred). |

---

## Permissions Required

### Microsoft Graph (Delegated)

| Permission | Purpose |
|------------|---------|
| `Tasks.ReadWrite` | Create, read, update Outlook tasks. |
| `User.Read` | Read user profile for authentication. |

Admin consent not required. User consents at first sign-in.

### Canvas

Personal Access Token grants full account access. Scopes are not granular.
