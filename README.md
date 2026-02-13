# Canvas to Outlook Task Sync

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Canvas LMS](https://img.shields.io/badge/Canvas-LMS-orange.svg)](https://www.instructure.com/canvas)
[![Microsoft 365](https://img.shields.io/badge/Microsoft-365-00A4EF.svg)](https://www.microsoft.com/microsoft-365)

A production-grade system that synchronizes Canvas LMS assignment completion status to Microsoft Outlook Tasks (Microsoft To Do). Built for students and educators who want their task list to reflect *actual* completion state—not just due dates.

---

## Table of Contents

- [What This System Does](#what-this-system-does)
- [Features at a Glance](#features-at-a-glance)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Setup Guide](#setup-guide)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Environment Variables Reference](#environment-variables-reference)
- [API Reference](#api-reference)
- [Common Issues](#common-issues)
- [FAQ](#faq)
- [Security](#security-considerations)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

---

## What This System Does

This tool automatically keeps your Outlook Tasks in sync with your Canvas assignments:

- **Creates tasks** for each Canvas assignment with course name, due date, and direct link
- **Marks tasks complete** when you submit assignments in Canvas
- **Reopens tasks** if a submission is removed or requires resubmission
- **Updates due dates** when Canvas assignments are rescheduled
- **Archives tasks** for deleted assignments (never loses data)

**Key Design Principle**: Tasks represent completion state, not just due dates. Your task list shows what you've actually done vs. what's pending.

## Features at a Glance

| Feature | Description |
|---------|-------------|
| **Completion Sync** | Task completion mirrors Canvas submission status in real-time |
| **Idempotent** | Safe to run every 30 min; never creates duplicates |
| **Diff-Based** | Only updates what changed—minimal API calls |
| **Failure Resilient** | One assignment error doesn't block others; survives restarts |
| **Dry-Run Mode** | Preview changes before applying |
| **Token Caching** | Microsoft auth persists; no login every run |
| **Archive, Not Delete** | Removed assignments are archived, never lost |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Canvas LMS    │────▶│   Sync Engine   │────▶│ Outlook Tasks   │
│   (Source of    │     │  (Diff-based,   │     │ (Microsoft To   │
│    Truth)       │     │   Idempotent)   │     │     Do)         │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  SQLite State   │
                        │    Store        │
                        └─────────────────┘
```

### Components

| Component | Purpose |
|-----------|---------|
| Canvas Client | Fetches courses, assignments, and submission status |
| Outlook Client | Creates and updates tasks via Microsoft Graph API |
| State Store | SQLite database tracking sync state for idempotency |
| Sync Engine | Diff-based logic determining minimal required changes |

## Prerequisites

- Python 3.10 or higher
- Canvas LMS account with API access
- Microsoft 365 account (personal or work/school)
- Azure app registration (free)

## Setup Guide

### Step 1: Generate Canvas Access Token

1. Log in to Canvas
2. Go to **Account** → **Settings**
3. Scroll to **Approved Integrations**
4. Click **+ New Access Token**
5. Enter a purpose (e.g., "Outlook Sync") and expiration date
6. Copy the token immediately (you won't see it again)

**Security Note**: Treat this token like a password. It has full access to your Canvas account.

### Step 2: Register Azure Application

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **+ New registration**
4. Configure:
   - **Name**: `Canvas Outlook Sync`
   - **Supported account types**: Choose based on your needs:
     - "Accounts in any organizational directory and personal Microsoft accounts" for most users
     - "Personal Microsoft accounts only" for personal accounts
   - **Redirect URI**: Select "Public client/native (mobile & desktop)" and enter `http://localhost:8400`
5. Click **Register**
6. Copy the **Application (client) ID** and **Directory (tenant) ID**

### Step 3: Configure API Permissions

1. In your app registration, go to **API permissions**
2. Click **+ Add a permission**
3. Select **Microsoft Graph** → **Delegated permissions**
4. Add these permissions:
   - `Tasks.ReadWrite` (required for creating/updating tasks)
   - `User.Read` (required for authentication)
5. Click **Add permissions**

**Note**: Admin consent is NOT required for these permissions.

### Step 4: Install Dependencies

```bash
cd canvas_outlook_sync

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 5: Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit with your values
nano .env  # or use your preferred editor
```

Required values:
```
CANVAS_BASE_URL=https://your-school.instructure.com
CANVAS_ACCESS_TOKEN=your_token_here
MICROSOFT_CLIENT_ID=your_azure_client_id
MICROSOFT_TENANT_ID=common
```

### Step 6: First Run

```bash
# Preview what will happen (no changes made)
python -m src.main --dry-run

# Run actual sync
python -m src.main
```

On first run, a browser window will open for Microsoft authentication. Sign in and grant the requested permissions.

## Usage

### Basic Commands

```bash
# Full sync
python -m src.main

# Preview changes without applying
python -m src.main --dry-run

# Verbose output (debug logging)
python -m src.main --verbose

# Show sync status
python -m src.main --status

# Re-authenticate with Microsoft
python -m src.main --reset-auth
```

### Scheduling (Recommended)

Run the sync automatically every 30-60 minutes:

**macOS/Linux (cron)**:
```bash
# Edit crontab
crontab -e

# Add line (runs every 30 minutes)
*/30 * * * * cd /path/to/canvas_outlook_sync && /path/to/venv/bin/python -m src.main >> logs/sync.log 2>&1
```

**Windows (Task Scheduler)**:
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Every 30 minutes
4. Action: Start a program
5. Program: `C:\path\to\venv\Scripts\python.exe`
6. Arguments: `-m src.main`
7. Start in: `C:\path\to\canvas_outlook_sync`

**macOS (launchd)**:
```xml
<!-- ~/Library/LaunchAgents/com.canvas.outlooksync.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.canvas.outlooksync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/python</string>
        <string>-m</string>
        <string>src.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/canvas_outlook_sync</string>
    <key>StartInterval</key>
    <integer>1800</integer>
    <key>StandardOutPath</key>
    <string>/path/to/canvas_outlook_sync/logs/sync.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/canvas_outlook_sync/logs/sync.log</string>
</dict>
</plist>
```

Load with: `launchctl load ~/Library/LaunchAgents/com.canvas.outlooksync.plist`

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CANVAS_BASE_URL` | Yes | — | Canvas instance URL (e.g. `https://school.instructure.com`) |
| `CANVAS_ACCESS_TOKEN` | Yes | — | Canvas Personal Access Token |
| `MICROSOFT_CLIENT_ID` | Yes | — | Azure AD application (client) ID |
| `MICROSOFT_TENANT_ID` | Yes | — | Azure tenant ID; use `common` for multi-tenant |
| `MICROSOFT_REDIRECT_URI` | No | `http://localhost:8400` | OAuth redirect URI (must match Azure app) |
| `MICROSOFT_TOKEN_CACHE` | No | `data/token_cache.json` | Path for cached auth tokens |
| `SYNC_TASK_LIST_NAME` | No | `Canvas Assignments` | Outlook task list name |
| `SYNC_DRY_RUN` | No | `false` | Set to `true` to preview without applying |
| `SYNC_MAX_RETRIES` | No | `3` | Max retries for API calls |
| `SYNC_RETRY_DELAY` | No | `1.0` | Seconds between retries |
| `STORAGE_DATABASE_PATH` | No | `data/sync_state.db` | SQLite database path |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

## How It Works

### Sync Logic

For each Canvas assignment, the engine:

1. **Loads stored state** from SQLite database
2. **Computes diff** between Canvas and stored state
3. **Applies minimal changes** to Outlook

| Canvas State | Action |
|-------------|--------|
| New assignment | Create Outlook task |
| Assignment submitted | Mark task completed |
| Submission removed | Reopen task |
| Due date changed | Update task due date |
| Assignment renamed | Update task title |
| Assignment deleted | Archive (NOT delete) |
| No change | No-op |

### Idempotency Guarantees

- **Safe to run multiple times**: Running twice produces same result
- **No duplicate tasks**: Unique (course_id, assignment_id) identity
- **Atomic state updates**: State saved after each successful operation
- **Partial failure recovery**: Errors don't corrupt other assignments

### Task Format

Created tasks include:
- **Title**: `[Course Name] Assignment Name`
- **Due Date**: From Canvas
- **Body/Notes**: Canvas assignment URL and IDs for reference

## Common Issues

### Authentication Errors

**"Interactive authentication required"**
- Run `python -m src.main --reset-auth` to clear cached tokens
- Ensure pop-up blockers aren't blocking the auth window

**"AADSTS50011: Reply URL mismatch"**
- Verify redirect URI in Azure matches `MICROSOFT_REDIRECT_URI` in `.env`
- Must be exactly `http://localhost:8400`

**"Insufficient privileges"**
- Check API permissions in Azure app registration
- Ensure `Tasks.ReadWrite` and `User.Read` are granted

### Canvas API Errors

**"401 Unauthorized"**
- Token may be expired; generate a new one
- Check `CANVAS_BASE_URL` is correct (no trailing slash)

**"403 Forbidden"**
- Token may lack required permissions
- Some institutions restrict API access

### Sync Issues

**"Tasks not updating"**
- Check `--dry-run` isn't enabled
- Run with `--verbose` to see detailed operations
- Verify the task list name matches `SYNC_TASK_LIST_NAME`

**"Duplicate tasks appearing"**
- This shouldn't happen with idempotent design
- Check if state database was deleted
- Verify task list name is consistent

### Data Issues

**"Want to start fresh"**
- Delete `data/sync_state.db` to reset state
- Delete tasks in Outlook manually
- Run sync again

## Security Considerations

### Secrets Management

- **Canvas token**: Full account access - keep secure
- **Azure credentials**: Client ID is not secret; tokens are cached locally
- **Token cache**: Contains refresh tokens; protect `data/token_cache.json`

### Best Practices

1. Never commit `.env` to version control
2. Use environment variables in CI/CD
3. Rotate Canvas token periodically
4. Review Azure app permissions regularly

### Permissions Used

| Permission | Scope | Purpose |
|------------|-------|---------|
| `Tasks.ReadWrite` | Delegated | Create, read, update tasks |
| `User.Read` | Delegated | Read user profile for auth |

No admin consent required. No access to email, calendar, or other data.

## Project Structure

```
canvas_outlook_sync/
├── src/
│   ├── canvas/           # Canvas LMS API client
│   │   ├── client.py     # HTTP client with retry logic
│   │   └── models.py     # Course, Assignment, Submission models
│   ├── outlook/          # Microsoft Graph API client
│   │   ├── client.py     # OAuth + task operations
│   │   └── models.py     # Task, TaskList models
│   ├── sync/             # Sync orchestration
│   │   ├── engine.py     # Main sync logic
│   │   └── diff.py       # Change detection
│   ├── storage/          # Persistent state
│   │   ├── state_store.py # SQLite operations
│   │   └── models.py     # SyncState model
│   └── main.py           # CLI entry point
├── config/
│   └── settings.py       # Configuration management
├── data/                 # Runtime data (gitignored)
│   ├── sync_state.db     # SQLite database
│   └── token_cache.json  # Microsoft auth tokens
├── .env.example          # Configuration template
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## Development

### Running Tests

```bash
# With dry-run mode
python -m src.main --dry-run --verbose

# Check sync status
python -m src.main --status
```

### Debugging

Enable verbose logging:
```bash
LOG_LEVEL=DEBUG python -m src.main --verbose
```

### Extending

The modular design allows easy extension:

- **Add new LMS**: Implement client similar to `canvas/client.py`
- **Add new destination**: Implement client similar to `outlook/client.py`
- **Custom sync logic**: Modify `sync/engine.py`

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## Acknowledgments

- Canvas LMS API documentation
- Microsoft Graph API documentation
- MSAL Python library
