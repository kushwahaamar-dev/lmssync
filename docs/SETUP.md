# Detailed Setup Guide

This guide walks you through configuring Canvas to Outlook Task Sync from scratch.

---

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] **Python 3.10+** — Check with `python3 --version`
- [ ] **Canvas LMS account** — From your institution (e.g., Texas Tech, university Canvas)
- [ ] **Microsoft account** — Personal (@outlook.com, @hotmail.com) or work/school (Microsoft 365)
- [ ] **Azure subscription** — Free tier is sufficient; use your Microsoft account

---

## Part 1: Canvas Access Token

The Canvas API uses Personal Access Tokens for authentication. Each token grants full access to your Canvas account.

### Step 1.1: Navigate to Token Settings

1. Log in to your Canvas instance (e.g., `https://your-school.instructure.com`)
2. Click your **profile/avatar** (top left)
3. Select **Settings**
4. Scroll to **Approved Integrations** (or **+ New Access Token**)

### Step 1.2: Create Token

1. Click **+ New Access Token**
2. **Purpose**: Enter a descriptive name (e.g., `Outlook Sync`, `LMS Sync`)
3. **Expiration**: Choose a date (90 days recommended; you can create new tokens)
4. Click **Generate Token**
5. **Copy the token immediately** — it will not be shown again

### Step 1.3: Store Securely

- Paste into your `.env` file as `CANVAS_ACCESS_TOKEN=...`
- Never commit the token to Git
- Regenerate if you suspect it was exposed

### Canvas Instance URL

Your `CANVAS_BASE_URL` is the root URL of your Canvas instance, e.g.:

- `https://texastech.instructure.com`
- `https://canvas.instructure.com` (Instructure-hosted)
- `https://canvas.yourschool.edu` (institution-hosted)

Use HTTPS only. Do not include a trailing slash.

---

## Part 2: Azure App Registration

You need an Azure AD app to authenticate with Microsoft Graph (Outlook Tasks).

### Step 2.1: Access Azure Portal

1. Go to [portal.azure.com](https://portal.azure.com)
2. Sign in with your Microsoft account
3. Search for **Azure Active Directory** (or **Microsoft Entra ID**)
4. Select **App registrations** in the left sidebar

### Step 2.2: Register New Application

1. Click **+ New registration**
2. Fill in:
   - **Name**: `Canvas Outlook Sync` (or any name)
   - **Supported account types**:
     - **"Accounts in any organizational directory and personal Microsoft accounts"** — for most users (work + personal)
     - **"Personal Microsoft accounts only"** — if using only personal Outlook
     - **"Accounts in this organizational directory only"** — work/school only
   - **Redirect URI**:
     - Platform: **Public client/native (mobile & desktop)**
     - URI: `http://localhost:8400` (must match exactly)
3. Click **Register**

### Step 2.3: Note Your IDs

After registration, you'll see:

- **Application (client) ID** — Use as `MICROSOFT_CLIENT_ID`
- **Directory (tenant) ID** — Use as `MICROSOFT_TENANT_ID`

For personal accounts or multi-tenant, you can use `MICROSOFT_TENANT_ID=common`.

### Step 2.4: Configure API Permissions

1. In your app, go to **API permissions**
2. Click **+ Add a permission**
3. Select **Microsoft Graph**
4. Choose **Delegated permissions**
5. Add:
   - `Tasks.ReadWrite` — Create and update Outlook tasks
   - `User.Read` — Read your profile (required for auth)
6. Click **Add permissions**

**Note**: Admin consent is NOT required for these scopes. You consent when you sign in.

### Step 2.5: Redirect URI Verification

Ensure `http://localhost:8400` is listed under **Authentication** → **Redirect URIs**. The app will open a local server briefly during the first sign-in to receive the auth callback.

---

## Part 3: Project Installation

### Step 3.1: Clone Repository

```bash
git clone https://github.com/kushwahaamar-dev/lmssync.git
cd lmssync
```

### Step 3.2: Create Virtual Environment (Recommended)

```bash
python3 -m venv venv

# Activate (macOS/Linux):
source venv/bin/activate

# Activate (Windows):
venv\Scripts\activate
```

### Step 3.3: Install Dependencies

```bash
pip install -r requirements.txt
```

Dependencies:

- `requests` — HTTP client for Canvas and Graph API
- `msal` — Microsoft Authentication Library (OAuth 2.0)

---

## Part 4: Environment Configuration

### Step 4.1: Create .env File

```bash
cp .env.example .env
```

### Step 4.2: Required Variables

Edit `.env` and set:

```env
# Canvas (required)
CANVAS_BASE_URL=https://your-school.instructure.com
CANVAS_ACCESS_TOKEN=your_token_from_step_1

# Microsoft (required)
MICROSOFT_CLIENT_ID=your_azure_client_id
MICROSOFT_TENANT_ID=common
```

### Step 4.3: Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MICROSOFT_REDIRECT_URI` | `http://localhost:8400` | OAuth redirect; match Azure |
| `MICROSOFT_TOKEN_CACHE` | `data/token_cache.json` | Path for cached tokens |
| `SYNC_TASK_LIST_NAME` | `Canvas Assignments` | Outlook task list name |
| `STORAGE_DATABASE_PATH` | `data/sync_state.db` | SQLite state file |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Part 5: First Run

### Step 5.1: Dry Run (Preview)

```bash
python -m src.main --dry-run
```

This fetches Canvas data and logs what would be created/updated, without making changes.

### Step 5.2: Full Sync

```bash
python -m src.main
```

On first run:

1. A browser window opens for Microsoft sign-in
2. Sign in with your Microsoft account
3. Approve the requested permissions
4. The app receives a token and caches it
5. Sync runs

Subsequent runs use the cached token (no browser) until it expires.

### Step 5.3: Verify

- Open [Outlook Tasks](https://to-do.office.com/) or Microsoft To Do app
- Look for a task list named **Canvas Assignments**
- Confirm tasks match your Canvas assignments

---

## Part 6: Scheduling (Optional)

To run sync automatically every 30 minutes, see the main [README](../README.md#scheduling-recommended) for cron, launchd, and Task Scheduler examples.

---

## Troubleshooting Setup

| Issue | Solution |
|-------|----------|
| `ConfigurationError: CANVAS_ACCESS_TOKEN is required` | Ensure `.env` exists and contains the token |
| `AADSTS50011: Reply URL mismatch` | Redirect URI in Azure must be exactly `http://localhost:8400` |
| Browser doesn't open for auth | Run with `--verbose`; check firewall; try `--reset-auth` |
| `401 Unauthorized` from Canvas | Token expired or invalid; generate a new one |

For more troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
