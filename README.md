# Enterprise Firefox Multi-Profile Management & Automation System

A modular, enterprise-grade Python automation platform designed for managing multiple independent, persistent Firefox browser profiles locally on Windows.

---

## 1. System Overview

This platform provides native execution of local Firefox instances with complete profile isolation, persistent cookies and sessions, encrypted account credential management, human-in-the-loop security verification (for CAPTCHAs, 2FA, and checkpoints), and a multi-agent orchestration architecture paired with a PySide6 desktop GUI dashboard.

### Key Architectural Tenets
- **Native Local Execution**: Executes installed Windows Firefox directly (`firefox.exe -profile <dir> -no-remote`). Zero remote or cloud browser dependencies.
- **Strict Profile Isolation**: Every profile operates in its own directory with dedicated `cookies.sqlite`, local storage, history, cache, certificates, and preferences.
- **Persistent Sessions**: Sessions, logins, and cookies persist naturally via Firefox's native storage. No automated clearing without explicit user instruction.
- **Zero Plaintext Passwords**: Credentials are encrypted using the Windows Credential Manager (`keyring`) with an authenticated AES-256-GCM fallback vault.
- **Human-in-the-Loop Verification**: Strictly adheres to security standards: When a CAPTCHA or security challenge appears, automation pauses, brings the Firefox window to front, and alerts the operator via the GUI dashboard to solve it manually.
- **Multi-Agent Architecture**: 8 specialized agents communicating through a central orchestrator.
- **Full Audit Trail**: Rotating file logs and structured SQLite audit tables.

---

## 2. Multi-Agent Architecture

The system is organized into a controlled multi-agent structure coordinated by `core/orchestrator.py`:

```
                           +--------------------------+
                           |   Central Orchestrator   |
                           +------------+-------------+
                                        |
       +--------------------+-----------+-----------+--------------------+
       |                    |                       |                    |
+------v-------+    +-------v--------+     +--------v-------+    +-------v--------+
| Agent 1      |    | Agent 2        |     | Agent 3        |    | Agent 4        |
| ProfileAgent |    | SessionManager |     | AccountAgent   |    | MonitoringAgent|
+--------------+    +----------------+     +----------------+    +----------------+
       |                    |                       |                    |
+------v-------+    +-------v--------+     +--------v-------+    +-------v--------+
| Agent 5      |    | Agent 6        |     | Agent 7        |    | Agent 8        |
| SecurityAgent|    | RecoveryAgent  |     | AuditLogger    |    | PySide6 GUI    |
+--------------+    +----------------+     +----------------+    +----------------+
```

1. **Agent 1: Profile Manager (`ProfileAgent`)**: Coordinates profile creation, directory provisioning, `user.js` preferences injection, launch, stop, restart, and deletion.
2. **Agent 2: Session Manager (`SessionManager`)**: Periodically inspects `cookies.sqlite` in read-only mode, tracks session expiration timestamps, and updates account statuses.
3. **Agent 3: Account Manager (`AccountAgent`)**: Links authorized service accounts to dedicated Firefox profiles and initiates interactive login flows.
4. **Agent 4: Browser Monitor (`MonitoringAgent`)**: Background daemon monitoring active processes, CPU%, and memory (MB) with configurable threshold alerts.
5. **Agent 5: Security Agent (`SecurityAgent`)**: Manages OS vault credentials, verifies directory filesystem isolation, and audits against symlink risks.
6. **Agent 6: Recovery Agent (`RecoveryAgent`)**: Detects browser crashes, purges stale `parent.lock` files, manages retry backoffs, and performs automated SQLite backups.
7. **Agent 7: Logging Agent (`AuditLogger`)**: Publishes structured audit logs to rotating disk files and the SQLite `audit_logs` table.
8. **Agent 8: GUI Agent (`DashboardWindow`)**: PySide6 desktop interface coordinating metrics, views, and human alerts.

---

## 3. Project Directory Structure

```
firefox_manager/
│   main.py                          # Application entry point (GUI + CLI modes)
│   requirements.txt                 # Project dependencies
│   README.md                        # Complete documentation
│
├── config/
│   └── settings.py                  # Pydantic v2 application settings & auto-path detection
│
├── core/
│   ├── orchestrator.py              # Central multi-agent coordinator & event bus
│   ├── process_manager.py           # Native process tracking, limits, CPU/RAM monitoring
│   ├── profile_manager.py           # High-level profile lifecycle engine
│   └── session_manager.py           # Persistent session inspection & expiration detection
│
├── agents/
│   ├── profile_agent.py             # Agent 1: Profile lifecycle & creation
│   ├── account_agent.py             # Agent 3: Account-to-profile management
│   ├── monitoring_agent.py          # Agent 4: Background resource monitor
│   ├── security_agent.py            # Agent 5: Credentials & isolation validation
│   └── recovery_agent.py            # Agent 6: Crash recovery & database backup
│
├── database/
│   ├── models.py                    # Pydantic schemas (Profile, Account, AuditLog, ProcessMetric)
│   └── database.py                  # Thread-safe SQLite engine with WAL mode & backups
│
├── browser/
│   ├── firefox_launcher.py          # Windows Firefox binary launcher & Win32 window focus
│   └── profile_storage.py           # Physical profile folders, user.js generator, parent.lock
│
├── authentication/
│   ├── manual_auth.py               # Interactive login coordinator in native Firefox
│   └── verification_handler.py      # Human-in-the-loop CAPTCHA/challenge handler
│
├── gui/
│   ├── dashboard.py                 # Modern PySide6 main window with live metric cards
│   ├── profile_view.py              # Profile table, creation modal, and action buttons
│   └── account_view.py              # Account table, mapping modal, and manual login trigger
│
├── security/
│   ├── credential_manager.py        # Windows Credential Manager + AES-256-GCM vault
│   └── audit_logger.py              # Rotating file logger + SQLite audit trail
│
├── tests/
│   ├── test_database.py             # Database CRUD, WAL mode, backups
│   ├── test_profile_storage.py      # Directory isolation, user.js, parent.lock
│   ├── test_credential_manager.py   # Encrypted vault, zero plaintext test
│   ├── test_profile_manager.py      # Duplicate prevention, lifecycle
│   ├── test_verification.py         # Human-in-the-loop pause & resume
│   └── test_orchestrator.py         # Agent initialization, event bus
│
├── data/                            # SQLite database storage (firefox_manager.db)
├── profiles/                        # Isolated Firefox profile directories
├── logs/                            # Rotating log files (firefox_manager.log)
└── backups/                         # Automated SQLite point-in-time snapshots
```

---

## 4. Installation & Setup

### Prerequisites
- Windows 10/11
- Python 3.12+ (Installed)
- Mozilla Firefox (Installed at `C:\Program Files\Mozilla Firefox\firefox.exe`)

### 1. Set Up Virtual Environment
```powershell
# Navigate to workspace
cd "c:\Users\Rimi\Desktop\Subwey"

# Create virtual environment with Python 3.12
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

---

## 5. Usage

### Launch Desktop GUI Dashboard
```powershell
.\.venv\Scripts\python.exe -m firefox_manager.main
```

### Run in CLI Mode
```powershell
# View real-time platform status summary
.\.venv\Scripts\python.exe -m firefox_manager.main --status

# List all managed profiles
.\.venv\Scripts\python.exe -m firefox_manager.main --list-profiles

# Create a new isolated profile
.\.venv\Scripts\python.exe -m firefox_manager.main --create-profile "ECommerce_Prod"

# Launch profile in Firefox
.\.venv\Scripts\python.exe -m firefox_manager.main --launch-profile "<PROFILE_ID>" --url "https://example.com"

# Stop a running profile
.\.venv\Scripts\python.exe -m firefox_manager.main --stop-profile "<PROFILE_ID>"

# Permanent Profile Deletion (Deletes from DB and completely wipes physical directory from disk)
.\.venv\Scripts\python.exe -m firefox_manager.main --delete-profile "<PROFILE_ID>"

# Native OS-Level Facebook Automated Login (Zero WebDrivers, Untouched Browser)
# The password is NEVER passed on the command line. Set it in the
# environment, or leave it unset and you will be prompted securely:
#   $env:FB_PASSWORD = "your-password"   # PowerShell (session only)
#   .\.venv\Scripts\python.exe -m firefox_manager.main --fb-login --profile "<PROFILE_ID>" --uid "<FB_UID_OR_EMAIL>"
# If FB_PASSWORD is not set, the CLI prompts with getpass (hidden input).
# The old --password argument has been removed.
.\.venv\Scripts\python.exe -m firefox_manager.main --fb-login --profile "<PROFILE_ID>" --uid "<FB_UID_OR_EMAIL>"

# Batch login from a file only (one UID:Password per line, file path only -
# inline credentials on the command line are refused)
.\.venv\Scripts\python.exe -m firefox_manager.main --batch-fb "C:\path\to\accounts.txt"

# Create database backup snapshot
.\.venv\Scripts\python.exe -m firefox_manager.main --backup
```

---

## 6. Running Automated Tests

Run the full pytest suite:
```powershell
.\.venv\Scripts\pytest.exe -v
```

All 23 unit and integration tests validate profile creation, isolation, session persistence, credential security, database backups, and human-in-the-loop challenge resolution.

## 7. Security

- **Leaked credential (must act now):** an earlier version of this repo contained a real Facebook login in plain text in `test_no_mouse.py`. That file has been replaced with a safe template that reads credentials only from the `FB_UID` / `FB_PASSWORD` environment variables or a `getpass()` prompt.
  1. **Change that Facebook password immediately** - it was in a public repository.
  2. **Purge it from git history** - deleting the file in a new commit is not enough; the old value is still in history. Use `git filter-repo` (or BFG Repo-Cleaner) to remove the file from all history, then force-push and rotate any other credentials that were in the repo.
  3. Check GitHub's secret-scanning / push-protection alerts for the repo.
- **Never commit credentials.** `.env` files, `vault.key`, `vault.enc`, `agent_memory.json`, and `test_no_mouse.py` are all in `.gitignore`. Passwords are accepted only via `FB_PASSWORD`, a `getpass()` prompt, or the OS vault - never as a CLI argument, never hardcoded, never logged.
- **Human-in-the-loop:** when Facebook shows a CAPTCHA, checkpoint, or 2FA challenge, automation pauses and waits (up to 300s) for you to solve it in the Firefox window. It never auto-solves CAPTCHAs and never enters verification codes. A login is only marked ACTIVE after the home page / session cookie is actually verified.
- **Vault key:** the AES fallback vault key is stored in the OS credential store (keyring) when available. A file fallback (`data/.vault/vault.key`, owner-only permissions) is used only when keyring is unavailable and is weaker - anyone who can read that folder can decrypt the vault, so prefer a machine with Windows Credential Manager.

