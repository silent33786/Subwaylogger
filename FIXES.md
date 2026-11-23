# Subwaylogger — fixes applied

Source: public clone of `https://github.com/silent33786/Subwaylogger`
(Windows Python Firefox multi-profile manager for Facebook login + Auto Ads).
This copy was made without `.git`, edited in place, and never pushed anywhere.
No Firefox window was launched and no Facebook login was attempted while
fixing it. Validation was `python3 -m py_compile` on every `.py` file only.

No real UID, email, or password appears in this file or anywhere in this
fixed copy. Values from the old code are referred to only as "the leaked
login" and are never reproduced.

## 1. `requirements.txt`
- Added `pywin32`, `Pillow`, and `pywinauto` — all three are imported by the
  code (`win32gui`/`win32service`/`win32con`, `PIL.Image`, `pywinauto`) but
  were missing, so a fresh install failed on import. `pywin32`/`pywinauto`
  are marked Windows-only (`sys_platform == "win32"`). Existing pins kept.

## 2. `test_no_mouse.py` (rewritten)
- **Removed the hardcoded real Facebook login** (a UID and a password in
  plain text, committed to a public repo). See "What you must still do".
- Replacement is a safe template: credentials only from `FB_UID` /
  `FB_PASSWORD` env vars or a `getpass()` prompt, never printed or logged,
  cleared from memory in a `finally` block.
- Added assertions (Firefox window must actually be found), a non-Windows
  early exit, and guaranteed Firefox cleanup in `finally` (the old code
  killed the process only via the `finally` too, but had no assertions and
  no platform guard).
- `firefox_manager/gui/automation_view.py`: the batch-tab placeholder
  contained example passwords (`MyPass123`-style dummy values). Replaced
  with format-only placeholders (`<uid-or-email>:<password>`), no values.

## 3. `firefox_manager/main.py`
- Removed the `--password` CLI argument entirely. `--fb-login` now takes
  the password only from the `FB_PASSWORD` env var or a hidden `getpass()`
  prompt (`_resolve_password()`), and clears it after use. A password on a
  command line lands in shell history and the process list.
- `--batch-fb` now accepts **only a file path**. Inline semicolon-delimited
  credentials on the command line are refused with a clear error.
- Fixed the `--delay or 6.0` bug: `--delay 0` used to become `6.0`.
  Now `None` (not given) → `6.0`, and `0.0` is honoured.
- `run_cli()` actions are wrapped in try/except: a failure prints a clean
  `Error: ...` and returns exit code 1 instead of a raw traceback.
  A failed login now returns 1 (it used to return 0 with `success: True`).
- Added `--delete-profile` (was documented in the README but had no CLI).
- `--cli` with no action now returns 2 with an error instead of silently
  returning 0. Running with no arguments still opens the GUI (original
  default); only the `--cli`-with-no-action path returns 2.

## 4. `firefox_manager/core/process_manager.py`
- Added the missing `import sys`. `stop_profile_process()` used
  `sys.platform` without importing it, so stopping any profile raised
  `NameError` and left the profile stuck in STOPPING.
- `shutdown_all()` no longer kills any Firefox whose cmdline merely
  contains `-profile`. It now only kills Firefox processes whose cmdline
  contains the managed `profiles_dir` — the old rule could kill the user's
  unrelated Firefox profiles.

## 5. `firefox_manager/config/settings.py`
- `base_dir` / `data_dir` / `profiles_dir` / `logs_dir` / `backups_dir` are
  now derived from `__file__` (project root), not `os.getcwd()`, so data
  lands in the same place regardless of where the program is launched from.
- Env overrides added: `FIREFOX_MANAGER_BASE_DIR` and `FIREFOX_BINARY`.
- `firefox_binary_path` may be `None` without crashing at import time.
  New `require_firefox_binary()` raises a clear error (install Firefox or
  set `FIREFOX_BINARY`) only at the point Firefox is actually launched.
- `signon.importedFromEdge` changed `True` → `False`. The old value claimed
  passwords had already been imported from Edge and could trigger import
  prompts — the opposite of the intended "disable import popups".
- The field validator no longer creates directories as a validation side
  effect; it only normalises the path. `ensure_all_dirs()` is still called
  once at startup and is idempotent.

## 6. `firefox_manager/browser/firefox_launcher.py`
- `import winreg` is guarded in try/except (`None` on non-Windows).
  Registry lookup is skipped when `winreg is None`.
- `__init__` no longer raises `FileNotFoundError` when Firefox is missing,
  so importing the app / running `--status` / `--help` / tests works on a
  machine without Firefox. The missing-binary error is stored and raised
  only in `launch()`, with a message telling the user how to fix it.

## 7. Windows-import guards (5 files)
`smart_vision.py`, `smart_locator.py`, `auto_ads_engine.py`,
`ad_pipeline_steps.py`, `ad_agent_recovery.py`: top-level
`win32gui` / `win32service` / `win32con` imports are wrapped in
try/except and set to `None` when pywin32 is absent. Functions that need
them raise a clear `RuntimeError` ("needs Windows + pywin32") only when
called, instead of crashing the whole import. `SmartVisionLocator`
also guards `ctypes.windll` access on non-Windows (`user32`/`gdi32`
are `None` there).

## 8. `firefox_manager/authentication/system_automation.py` (core login)
- Removed the duplicated `force_focus_window()` + log calls in
  `run_facebook_login_system_level()`.
- `paste_into_focused_input()` now checks `set_clipboard()`'s return
  value. If the clipboard could not be set it raises `RuntimeError`
  instead of sending Ctrl+V and pasting stale clipboard content
  (possibly the previous credential) into the wrong field.
- **Account is no longer marked ACTIVE and the password is no longer
  saved to the vault before the login is verified.** Both now happen
  only after `home_page_reached` is True. On failure the account is
  set to `REQUIRES_LOGIN` so the dashboard never shows a false
  "connected" account.
- **Return value is honest:** `{"success": False, ...}` when the home
  page was not reached. It used to return `success: True` with
  "Credentials submitted." even on failure / challenge.
- **Human-in-the-loop now actually waits.** When a challenge is
  detected, the code calls
  `verification_handler.request_human_verification()` **and waits** on
  `req.wait_for_resolution(timeout=300)`. If it times out it returns
  `success: False, message: "verification not completed"`. No CAPTCHA
  or 2FA code is ever solved or entered by automation; the user solves
  it in the Firefox window. After a resolved challenge the monitor
  window restarts so a second challenge can be caught.
- `check_facebook_session_status()`: no longer queries for a cookie
  literally named `checkpoint` — no such cookie reliably signals a
  checkpoint, so that check almost never fired. Logged-in is decided
  only by the `c_user` session cookie; checkpoint detection comes from
  the window title (documented in the code). The weak title-only
  "home page" shortcut was also removed: a title of exactly `facebook`
  only counts together with a `c_user` cookie.
- `run_batch_facebook_automation()`:
  - Stops the previous account's Firefox before starting the next one
    (old code never stopped it, so profiles piled up until the
    concurrent-profile limit was hit and later accounts failed), and
    enforces `max_concurrent_profiles` up front with a clear per-account
    error instead of a confusing launch failure.
  - Parsing splits on the **first** separator only (old code tried
    separators in order and could split a password containing `:` at the
    wrong place).
  - Lines with an empty username or password are now reported as
    skipped-account entries instead of being silently dropped.
  - Per-account `success` now follows the login result instead of
    recording success for every non-exception return.

## 9. `firefox_manager/security/credential_manager.py`
- `_ensure_encryption_key()` now **always sets `self._master_key`**. The
  old code only set it when the key file already existed, leaving the
  attribute missing on a fresh vault.
- The master key is now stored in the OS credential store (keyring,
  service `FirefoxManager_vault_key`) first. An existing file key is
  migrated into keyring when possible. A file fallback is written only
  when keyring is unavailable, with `0o600` owner-only permissions.
  **Warning: a file-stored key is weaker** — anyone who can read that
  folder can decrypt the vault. Prefer a machine with Windows
  Credential Manager. The old code wrote the key as a plain file next
  to the encrypted vault with no permissions, defeating the encryption.
- Removed the unused `PBKDF2HMAC` / `hashes` imports: they implied a
  password-derived key that never happened. The key is a random 256-bit
  key from `AESGCM.generate_key`, stated honestly in the docstring.
- `_get_fallback_key()` now returns the in-memory key instead of
  re-reading the file each time. Vault files are also written `0o600`.

## 10. `firefox_manager/browser/profile_storage.py`
- `_validate_directory_name()` (enforced in `get_profile_path()`):
  rejects absolute paths, `/`, `\`, `..`, and empty names with
  `ValueError`. The old code joined the name onto the profiles dir
  unchecked, so a crafted name could make create/delete operate
  outside `profiles/` — including wiping an arbitrary folder.
- `_configure_proxy_prefs()` rewritten with `urllib.parse`: handles
  `host:port`, `scheme://host:port`, `user:pass@host:port`, and IPv6
  `[::1]:port`. Unparseable input now raises `ValueError` with a clear
  message instead of silently leaving the profile with no proxy.
- `delete_profile_directory()` no longer runs `cmd.exe /c rd` with a
  shell or a PowerShell `Remove-Item` with the path interpolated into a
  command string (shell-injection hole). It uses `shutil.rmtree` only,
  with the read-only handler and retries.

## 11. Auto Ads — honest verification
`firefox_manager/automation/ad_pipeline_steps.py`:
- `BaseAdStep.verify()` default is now `False`, not `True`: a step that
  never implemented verification must fail loudly.
- `NavigateAdCenterStep.verify()` returns `False` (was `True`) when the
  ad form is not active after retries, so the engine retries/fails
  instead of continuing as if the form were open.
- `UnlockProfileStep.verify()` passes only if the "Unlock profile"
  control is no longer present.
- `ProfessionalModeStep.verify()` passes only if Pro Mode is disabled
  in config or is actually detectable as active.
- `SetGoalStep.verify()` / `FillCreativeStep.verify()` /
  `AudienceBudgetStep.verify()` now check real observables (ad form
  still active + the expected control/field present via UIA) instead of
  returning `True` unconditionally. Exact field *values* cannot be read
  back without DOM access in native mode — that limit is logged in the
  code, not hidden behind a `True`.
- `PublishStep.verify()` fails if the ad form is still active after
  Publish (publish did not go through), and still raises
  `NeedsHumanChallenge` for checkpoint/payment titles.
- **Fake EU payee removed.** `RANDOM_PAYEE_NAMES` is deleted. If an EU
  country is targeted and no `payee_name` is supplied,
  `AudienceBudgetStep` raises `ValueError` asking for the real legal
  payee name. The automation will not invent a company name for a
  compliance declaration.
- `FillCreativeStep` CTA: the bare `except: pass` is gone. A failed CTA
  is logged and re-raised so the step fails instead of silently
  continuing without a CTA.
- `firefox_manager/automation/auto_ads_engine.py`:
  - Final return when a challenge is present is now
    `{"success": False, "paused": True, message: "Paused for
    verification/payment — ad NOT submitted"}`. It used to say
    `success: True` / "Ad submitted!".
  - Human-challenge / policy / security pauses no longer consume a
    retry attempt. The retry loop is now a `while` loop where only a
    genuine failure increments the attempt counter; waiting on the user
    does not burn one of the 3 attempts.
  - `wait_for_page_ready()` now polls the window title every 0.5s and
    returns early once the title is stable and non-empty for two
    consecutive polls, instead of blindly sleeping the whole duration.
  - `maximize_browser_window()`, `navigate_browser_to_url()`, and
    `scroll_mouse()` guard missing Win32 APIs with clear errors.
- `firefox_manager/tests/test_auto_ads.py`: updated — it imported the
  removed `RANDOM_PAYEE_NAMES`. It now asserts the fake-payee list does
  not exist in either module.

## 12. `firefox_manager/automation/smart_vision.py`
- Grey-button range tightened so it no longer matches Facebook's page
  background `#F0F2F5` (240, 242, 245), which the old range
  (215–240, 220–242, 225–246) matched exactly — the whole page used to
  qualify as one giant "button". New range targets the actual
  secondary-button fill with a bounded button-sized cluster.
- Red-pixel restriction check now requires a **dense** cluster (≥40 red
  pixels inside a single 120×60 window, i.e. a real banner), not just
  ≥15 scattered red pixels anywhere — any red badge/avatar used to
  trigger a false "account restricted" pause.
- `capture_window_image()` GDI leaks fixed: the previously selected
  bitmap is restored into the memory DC before `DeleteObject`, and the
  DC / bitmap / window DC are released on **every** path via `finally`
  (previously leaked on early returns). The image is also copied before
  the pixel buffer is freed. `attach_to_desktop()` now closes the
  desktop handle it opens.
- `find_color_button_center()` returns `None` instead of crashing when
  Win32 is unavailable.

## 13. `firefox_manager/automation/smart_locator.py`
- `coord=` is no longer an auto-success fallback. `find()` tries
  colour/UIA candidates first within the timeout; coordinates are tried
  **last**, only if no real candidate resolved, with a warning log that
  the caller must still verify after clicking. Coordinates always
  "resolve", so treating them as a found element used to click blindly.
- UIA `title_re` now uses `re.escape(title)`: the old code interpolated
  the raw title into a regex, so titles containing `(`, `+`, etc. broke
  matching or matched the wrong control.
- `find()` now respects `timeout` for colour search too (deadline
  checked between candidates), instead of ignoring it for SmartVision.

## 14. `firefox_manager/automation/ad_agent_memory.py`
- Added a best-effort cross-process file lock (atomic `.lock` directory
  with stale-lock expiry + 10s timeout) around load/save. The old code
  had only a per-instance threading lock, so two processes writing at
  once silently lost each other's updates.
- `save()` re-reads and merges on-disk data under the lock before
  writing, instead of blindly overwriting it.
- `score()` no longer mutates data (it used `setdefault` on read, so
  merely ranking candidates created a key for every candidate ever
  considered). Reads now use a non-mutating peek; `get_stats()` builds
  its numbers from a snapshot copy.

## 15. `README.md`
- Test count corrected: 15 → **23** (actual `def test_` count in
  `firefox_manager/tests/`).
- Documents the new login flow: no `--password` argument, `FB_PASSWORD`
  env var or `getpass()` prompt; `--batch-fb` takes a file path only;
  `--delete-profile` documented.
- New **Security** section: rotate the leaked password, purge git
  history with `git filter-repo` / BFG, never commit credentials,
  human-in-the-loop rules, and the vault-key warning.

## 16. `.gitignore`
- Added `.env`, `*.env`, `vault.key`, `vault.enc`, `agent_memory.json`
  (+ `.tmp`), `test_no_mouse.py`, and `accounts.txt` patterns, so no
  credential file can be committed by accident.

## Validation performed
- `python3 -m py_compile` on all 47 `.py` files in the fixed copy: **PASS**.
- Grep (counts only, no values printed): 0 files contain a 14+-digit
  number; 0 `--password` argparse arguments; 0 `shell=True` in code;
  0 example passwords in the GUI; 0 literal credential arguments in
  `test_no_mouse.py`; 0 `random.` uses left in the pipeline.
- Every `verify()` in `ad_pipeline_steps.py` now returns `True` only
  after a real check (or for a feature explicitly disabled in config,
  e.g. Pro Mode off / unlock check off). The only unconditional `True`
  left is gone: the base-class default is now `False`.
- `__pycache__` folders created by `py_compile` were removed from the
  fixed copy afterwards.

## 17. Test-run fix (found while testing on Linux, 2026-11-23)
- `AdAgentMemory.clear()` did nothing: `save()` merged the old on-disk
  data back in, resurrecting the cleared entries, so the memory test
  failed after `clear()` (`score` stayed 0.667 instead of returning
  to 0.5). `save()` now takes `merge=True/False` and `clear()` calls
  `save(merge=False)`.

## Test run on Linux (2026-11-23, this PC)
- Fresh venv, installed only `pydantic psutil cryptography keyring
  pytest pytest-asyncio Pillow` (PySide6 / pywin32 are Windows-only
  and were not installed). Ran with
  `FIREFOX_MANAGER_BASE_DIR=/tmp/test-run-data` so no test data
  touched the fixed copy.
- `pytest firefox_manager/tests -v`: **23 passed, 0 failed** after
  the fix in section 17 (first run was 22 passed, 1 failed — the
  `clear()` bug above).
- CLI `--help`: no `--password` argument, `--delete-profile` present,
  `--fb-login` documented as env/getpass only.
- CLI `--status`: works on Linux with no Firefox installed, exit 0,
  0 profiles / 0 accounts.
- CLI create → list → delete profile round-trip: works, profile
  deleted from DB and disk, list back to 0.
- CLI `--fb-login` with a fake profile and `FB_PASSWORD` env set:
  clean `Error: Profile 'no-such-id' not found.`, exit 1, no
  traceback, no Firefox launched.
- CLI `--fb-login --password ...`: rejected as unrecognized argument.
- `profile_storage.get_profile_path('../evil')`: raises `ValueError`
  as intended.
- `paste_into_focused_input()` on Linux (no Win32): raises
  `RuntimeError` refusing to paste stale content, as intended.
- NOT tested here (needs Windows + Firefox + a real Facebook
  account): actual Facebook login, CAPTCHA / checkpoint pause-and-
  wait, Auto Ads end-to-end, and the GUI. Those still need a Windows
  test run by Ahmed.
- Changed files (19, vs the source clone): `.gitignore`, `README.md`,
  `requirements.txt`, `test_no_mouse.py`,
  `firefox_manager/main.py`,
  `firefox_manager/authentication/system_automation.py`,
  `firefox_manager/automation/ad_agent_memory.py`,
  `firefox_manager/automation/ad_agent_recovery.py`,
  `firefox_manager/automation/ad_pipeline_steps.py`,
  `firefox_manager/automation/auto_ads_engine.py`,
  `firefox_manager/automation/smart_locator.py`,
  `firefox_manager/automation/smart_vision.py`,
  `firefox_manager/browser/firefox_launcher.py`,
  `firefox_manager/browser/profile_storage.py`,
  `firefox_manager/config/settings.py`,
  `firefox_manager/core/process_manager.py`,
  `firefox_manager/gui/automation_view.py`,
  `firefox_manager/security/credential_manager.py`,
  `firefox_manager/tests/test_auto_ads.py`.

## What you must still do
1. **Rotate the leaked Facebook password NOW.** It was in a public
   repository. Changing it in the app is not enough.
2. **Purge git history.** Deleting the file in a new commit does not
   remove it from history. Use `git filter-repo --path test_no_mouse.py
   --invert-paths` (or BFG Repo-Cleaner), then force-push, and check
   GitHub secret-scanning alerts. Anyone who cloned the repo while it
   was public may still have the old file.
3. **Install the new requirements on Windows:** create a fresh venv and
   run `pip install -r requirements.txt` (adds pywin32, Pillow,
   pywinauto). The old venv will fail on the new imports.
4. **Test on Windows.** This fix was validated by syntax check only
   (Linux VM, no Firefox, no Facebook login, per the task limits).
   On Windows, test in this order: `--status`, `--create-profile`,
   `--fb-login` with `FB_PASSWORD` set (expect a pause if Facebook
   shows a challenge — solve it yourself in Firefox, the run now waits
   up to 300s), then one Auto Ads run on a throwaway profile and check
   the dashboard no longer reports success for a failed step.
5. **Re-check the vault on first run.** If an old `data/.vault/vault.key`
   file exists from the old version, the new code migrates it into
   keyring when possible; delete the file afterwards if keyring is
   working, so the weaker file fallback is gone.
6. **Review the Publish verify behaviour.** It now fails if the ad form
   is still active after Publish. If Facebook shows a confirmation
   screen that still counts as "ad form active", that step will retry
   and then fail honestly rather than claiming success — check it once
   on a real run and adjust the observable if needed.

## What was NOT fixed (and why)
- **No live Windows/Firefox/Facebook testing.** The task forbade
  launching Firefox or logging into Facebook, and this machine is
  Linux. All behaviour changes above are code-level fixes validated by
  `py_compile` only; a real Windows run is still needed (see step 4).
- **Value-level verify without DOM access.** In native (no-WebDriver)
  mode there is no DOM, so SetGoal / FillCreative / AudienceBudget
  verify form + field presence, not the exact entered values. That
  limit is logged in the code rather than hidden.
- **`coord=` candidates still exist in pipeline step definitions.**
  They are now last-resort only (SmartLocator tries colour/UIA first
  and warns), because several steps have no other candidate for some
  controls. Removing them entirely would make those steps
  unfindable; replacing them needs real UIA names for those controls,
  which requires a live Facebook UI inspection on Windows.
- **Clipboard paste still assumes the login field has focus** (Tab
  order email → password). Without DOM access focus cannot be proven;
  the fix is that a failed clipboard set now raises instead of pasting
  stale content, and a failed login is reported as failed.
- **GUI workers pass passwords in memory** (Qt password fields →
  worker threads). That is the GUI's existing design; the CLI/file
  leaks were fixed, but a full in-memory credential hygiene pass on
  the GUI was out of scope for this round.
- **Colour-based button detection is still heuristic.** The ranges are
  tightened, but a Facebook UI colour change can break it again. UIA
  candidates are tried first wherever they exist.
