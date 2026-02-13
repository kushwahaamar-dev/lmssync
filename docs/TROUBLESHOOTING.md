# Troubleshooting Guide

Common issues and how to resolve them.

---

## Authentication Issues

### "Interactive authentication required" (Microsoft)

**Cause**: Cached tokens expired or invalid; first run without cache.

**Solutions**:

1. **Clear token cache and re-authenticate**:
   ```bash
   python -m src.main --reset-auth
   python -m src.main
   ```

2. **Check pop-up blockers** — Browser must open for Microsoft sign-in. Allow pop-ups for localhost.

3. **Verify redirect URI** — In Azure Portal, app **Authentication** → Redirect URIs must include exactly `http://localhost:8400`.

---

### "AADSTS50011: Reply URL mismatch"

**Cause**: The redirect URI in your request does not match the one registered in Azure.

**Solutions**:

1. In Azure Portal → Your app → **Authentication**
2. Under **Redirect URIs**, ensure `http://localhost:8400` is listed
3. Platform must be **Public client/native (mobile & desktop)**
4. In `.env`, set: `MICROSOFT_REDIRECT_URI=http://localhost:8400`
5. No trailing slash, use `http` not `https` for localhost

---

### "Insufficient privileges" (Microsoft Graph)

**Cause**: App lacks required permissions.

**Solutions**:

1. Azure Portal → Your app → **API permissions**
2. Ensure these **Delegated** permissions are added:
   - `Tasks.ReadWrite`
   - `User.Read`
3. Click **Grant admin consent** (if in org) or re-consent when signing in
4. Run `python -m src.main --reset-auth` and sign in again

---

### "401 Unauthorized" (Canvas)

**Cause**: Invalid or expired Canvas token.

**Solutions**:

1. Generate a new token: Canvas → Account → Settings → Approved Integrations → New Access Token
2. Update `CANVAS_ACCESS_TOKEN` in `.env`
3. Ensure `CANVAS_BASE_URL` has no trailing slash and uses HTTPS

---

### "403 Forbidden" (Canvas)

**Cause**: Token valid but lacks permission, or institution restricts API.

**Solutions**:

1. Confirm token was created for your account
2. Check if your institution disables API access
3. Try a different Canvas instance if testing with multiple schools

---

## Sync Issues

### Tasks not appearing in Outlook

**Checklist**:

1. **Dry run?** — Ensure `--dry-run` is not set. Run: `python -m src.main`
2. **Task list name** — Default is `Canvas Assignments`. Check Outlook for that list.
3. **Verbose output** — Run `python -m src.main --verbose` to see create/update logs
4. **Account** — Ensure you signed in to the same Microsoft account you’re checking in Outlook/To Do

---

### Duplicate tasks

**Cause**: State database was deleted or task list name changed.

**Solutions**:

1. Use a consistent `SYNC_TASK_LIST_NAME` in `.env`
2. Do not delete `data/sync_state.db` unless intentionally resetting
3. If duplicates exist: delete them in Outlook, delete `data/sync_state.db`, run sync to rebuild state

---

### Tasks not marking complete when submitted in Canvas

**Possible causes**:

1. **Sync frequency** — Sync runs only when you execute it. Schedule it (cron, Task Scheduler) for automatic updates.
2. **Submission detection** — Sync uses `submitted_at` and `workflow_state`. Some assignment types (e.g., external tools) may not report these; check Canvas submission status.
3. **Verbose run** — `python -m src.main --verbose` to confirm submission state is being read

---

### Assignments missing from sync

**Possible causes**:

1. **Unpublished assignments** — Sync skips unpublished assignments. Publish in Canvas to include them.
2. **Course enrollment** — Only assignments from **active** enrollments are fetched.
3. **Pagination** — Large course loads are paginated; check logs for errors during fetch.

---

## Configuration Issues

### "ConfigurationError: CANVAS_ACCESS_TOKEN is required"

**Solutions**:

1. Create `.env` from `.env.example`: `cp .env.example .env`
2. Add `CANVAS_ACCESS_TOKEN=your_token`
3. Ensure no spaces around `=`
4. If using a different path, load via `--env /path/to/.env`

---

### "ConfigurationError: CANVAS_BASE_URL is required"

**Solutions**:

1. Set `CANVAS_BASE_URL=https://your-school.instructure.com` in `.env`
2. Use HTTPS
3. No trailing slash

---

### Environment variables not loading

**Solutions**:

1. Place `.env` in the project root (same directory as `src/`)
2. Or pass explicitly: `python -m src.main --env /path/to/.env`
3. Ensure `.env` is not in `.gitignore` for local use (it should be gitignored for security)

---

## Data & State Issues

### Want to start fresh

**Steps**:

1. Delete local state: `rm data/sync_state.db`
2. Optionally delete the `Canvas Assignments` task list in Outlook
3. Run sync: `python -m src.main`
4. All assignments will be re-created as new tasks

---

### Wrong task list being used

**Solutions**:

1. Set `SYNC_TASK_LIST_NAME` in `.env` to the desired list name
2. Sync creates the list if it doesn’t exist
3. To switch lists: create the new list in Outlook first, or set the name and run sync; old list will remain but won’t be updated

---

## Debugging

### Enable verbose logging

```bash
LOG_LEVEL=DEBUG python -m src.main --verbose
```

### Check sync status

```bash
python -m src.main --status
```

Shows: total assignments, active, archived, submitted vs pending.

### Inspect state database

```bash
sqlite3 data/sync_state.db "SELECT * FROM sync_state LIMIT 10;"
```

### Test Canvas connection

```python
# Quick test script
from src.canvas.client import CanvasClient
import os
client = CanvasClient(
    base_url=os.getenv("CANVAS_BASE_URL"),
    access_token=os.getenv("CANVAS_ACCESS_TOKEN"),
)
courses = client.get_active_courses()
print(f"Found {len(courses)} courses")
```

---

## Performance

### Sync is slow

- Canvas and Microsoft rate limits apply
- Many courses/assignments increase fetch time
- Run sync less frequently (e.g., every 60 minutes) if appropriate
- Use `--dry-run` to validate logic without waiting for API writes

### Database locked

- SQLite uses WAL; normally one writer
- Ensure only one sync process runs at a time
- If using cron, avoid overlapping runs (e.g., `flock` or similar)

---

## Getting Help

If issues persist:

1. Run with `--verbose` and save the log
2. Check [GitHub Issues](https://github.com/kushwahaamar-dev/lmssync/issues)
3. Include: Python version, OS, and relevant log excerpts (no tokens)
