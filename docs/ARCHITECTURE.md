# Architecture

Technical deep-dive into the Canvas to Outlook Task Sync system.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           SYNC PIPELINE                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Canvas LMS          Sync Engine              Outlook (Microsoft To Do)   │
│  ┌─────────┐        ┌─────────────┐          ┌─────────────────┐         │
│  │ Courses │───────▶│   Diff      │─────────▶│  Task List      │         │
│  │ Assign  │        │   Engine    │          │  "Canvas Assign"│         │
│  │ Submit  │        └──────┬──────┘          │  ┌───────────┐  │         │
│  └─────────┘               │                 │  │  Tasks    │  │         │
│                            │                 │  └───────────┘  │         │
│                            ▼                 └─────────────────┘         │
│                    ┌───────────────┐                                      │
│                    │  State Store  │                                      │
│                    │  (SQLite)     │                                      │
│                    └───────────────┘                                      │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Fetch Phase

```
Canvas API                    Canvas Client
────────────                  ─────────────
/api/v1/courses     ────────▶  get_active_courses()
  ?enrollment_state=active

/api/v1/courses/{id}/assignments  ──▶  get_assignments(course)
  ?include[]=submission
```

For each active course, assignments are fetched with submission data in a single request (using `include[]=submission`). This minimizes API calls.

### 2. Diff Phase

For each Canvas assignment `(course_id, assignment_id)`:

1. **Load state** from SQLite: `SELECT * FROM sync_state WHERE canvas_course_id = ? AND canvas_assignment_id = ?`
2. **Compute diff**:
   - No state → `NEW_ASSIGNMENT` (create task)
   - State exists → compare: submission, due_date, title
3. **Output**: List of actions (create, update, no-op)

### 3. Apply Phase

| Diff Result | Action | Outlook API |
|-------------|--------|-------------|
| `NEW_ASSIGNMENT` | Create task | `POST /me/todo/lists/{id}/tasks` |
| `SUBMITTED` | Mark complete | `PATCH .../tasks/{id}` `status: completed` |
| `UNSUBMITTED` | Reopen | `PATCH .../tasks/{id}` `status: notStarted` |
| `DUE_DATE_CHANGED` | Update due date | `PATCH .../tasks/{id}` `dueDateTime` |
| `TITLE_CHANGED` | Update title | `PATCH .../tasks/{id}` `title` |
| `NO_CHANGE` | Skip | — |

### 4. Persist Phase

After each successful Outlook operation:

```sql
INSERT OR REPLACE INTO sync_state (
  canvas_course_id, canvas_assignment_id, outlook_task_id,
  last_seen_submission_state, last_seen_due_date, last_seen_title,
  last_synced_at, is_archived, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
```

---

## Identity Model

### Canvas Assignment Identity

Assignments are uniquely identified by:

```
(canvas_course_id, canvas_assignment_id)
```

**Never** use assignment names for identity—they can change. The composite key is stable.

### Outlook Task Linkage

Tasks store metadata in the body/notes:

```
Canvas Assignment
================
Course ID: 12345
Assignment ID: 67890
URL: https://canvas.example.com/...
```

This allows traceability and debugging. The primary link is the `sync_state` table mapping `(course_id, assignment_id) → outlook_task_id`.

---

## State Store Schema

```sql
CREATE TABLE sync_state (
  canvas_course_id INTEGER NOT NULL,
  canvas_assignment_id INTEGER NOT NULL,
  outlook_task_id TEXT,
  last_seen_submission_state TEXT DEFAULT 'not_submitted',
  last_seen_due_date TEXT,
  last_seen_title TEXT,
  last_synced_at TEXT,
  is_archived INTEGER DEFAULT 0,
  created_at TEXT,
  PRIMARY KEY (canvas_course_id, canvas_assignment_id)
);
```

- **WAL mode** — Write-Ahead Logging for better concurrent access
- **Atomic writes** — Each sync operation persists before moving to next
- **Archived flag** — Deleted Canvas assignments are marked archived, not removed

---

## Idempotency Guarantees

### Create Idempotency

- State is checked before create
- If `outlook_task_id` exists for `(course_id, assignment_id)` → skip create
- State is saved only after successful create

### Update Idempotency

- Only changed fields are sent (minimal PATCH payload)
- Re-running with same data sends same updates
- State is saved only after successful update

### Restart Safety

- If sync crashes mid-run, next run:
  - Loads last persisted state
  - Re-computes diff from current Canvas data
  - Applies only what's needed
- No orphaned or duplicate tasks

---

## Error Handling Strategy

| Error Type | Behavior |
|------------|----------|
| Config/Auth | Fail fast, exit with code 1 |
| Canvas 401/403 | Fail fast (token invalid) |
| Canvas 429 (rate limit) | Retry with backoff |
| Graph 429 | Retry with Retry-After header |
| Graph 401 | Refresh token, retry once |
| Per-assignment failure | Log, continue with others |
| Transient (5xx, timeout) | Retry up to `SYNC_MAX_RETRIES` |

---

## Authentication Flow

### Canvas

- **Bearer token** in `Authorization` header
- No refresh; tokens are long-lived (user creates new when expired)

### Microsoft (OAuth 2.0 + MSAL)

1. **First run**: Interactive flow
   - Opens browser
   - User signs in
   - Redirects to `http://localhost:8400` with code
   - App exchanges code for access + refresh tokens

2. **Cached run**: Silent flow
   - MSAL loads token from `token_cache.json`
   - Uses refresh token if access token expired
   - No browser required

3. **Token cache**: Stored in `data/token_cache.json` (gitignored)

---

## Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `config/settings` | Load env vars, validate, never log secrets |
| `canvas/client` | HTTP + pagination + retry for Canvas API |
| `canvas/models` | Course, Assignment, Submission dataclasses |
| `outlook/client` | MSAL auth + Graph API for tasks |
| `outlook/models` | TaskList, OutlookTask, TaskStatus |
| `storage/state_store` | SQLite CRUD, atomic persist |
| `sync/diff` | Compare assignment vs state → ChangeType |
| `sync/engine` | Orchestrate fetch → diff → apply → persist |
| `src/main` | CLI, logging, wiring |

---

## Extensibility

### Adding Another LMS

1. Implement `LMSClient` with `get_assignments() -> list[Assignment]`
2. Map LMS assignment model to `(course_id, assignment_id)` identity
3. Wire into sync engine (or create adapter)

### Adding Another Destination

1. Implement `TaskClient` with `create_task()`, `update_task()`, `complete_task()`, etc.
2. Map `OutlookTask` or equivalent
3. Wire into sync engine apply phase

### Custom Sync Logic

- Modify `sync/diff.py` for new `ChangeType` variants
- Extend `sync/engine.py` `_process_assignment()` for new actions
