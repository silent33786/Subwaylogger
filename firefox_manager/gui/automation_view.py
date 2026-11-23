"""
High-Contrast, Clear OS-Level Automation Studio.
Supports:
- Bulk / Batch Account Processing: User enters list of IDs & Passwords.
  System automatically creates an isolated Firefox profile for each ID,
  launches native Firefox, and types credentials at the OS level!
- Single Account Fast Run.
- Live real-time terminal output with progress indicator.
"""

from typing import Optional, List
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTextEdit,
    QCheckBox,
    QSpinBox,
    QFrame,
    QMessageBox,
    QProgressBar,
    QTabWidget,
    QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

from firefox_manager.core.orchestrator import orchestrator
from firefox_manager.authentication.system_automation import system_automation


class BatchWorker(QThread):
    """Background worker executing batch profile creation & OS login."""

    log_signal = Signal(str)
    progress_signal = Signal(int, int)  # current, total
    finished_signal = Signal(bool, str)

    def __init__(self, account_lines: List[str], page_delay: int, pause_delay: int):
        super().__init__()
        self.account_lines = account_lines
        self.page_delay = page_delay
        self.pause_delay = pause_delay

    def run(self):
        try:
            res = system_automation.run_batch_facebook_automation(
                account_lines=self.account_lines,
                page_load_delay=float(self.page_delay),
                delay_between_accounts=float(self.pause_delay),
                status_callback=lambda msg: self.log_signal.emit(msg),
                progress_callback=lambda cur, tot: self.progress_signal.emit(cur, tot),
            )
            msg = f"Completed: {res.get('succeeded', 0)} of {res.get('total', 0)} accounts succeeded."
            self.finished_signal.emit(True, msg)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class SingleWorker(QThread):
    """Background worker for single account run."""

    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, profile_id: str, uid: str, password: str, delay: int):
        super().__init__()
        self.profile_id = profile_id
        self.uid = uid
        self.password = password
        self.delay = delay

    def run(self):
        try:
            res = system_automation.run_facebook_login_system_level(
                profile_id=self.profile_id,
                username_or_uid=self.uid,
                password=self.password,
                page_load_delay=float(self.delay),
                status_callback=lambda msg: self.log_signal.emit(msg),
                save_to_vault=True,
            )
            self.finished_signal.emit(res.get("success", False), res.get("message", "Done"))
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class AutomationView(QWidget):
    """Clean, high-contrast OS Automation Dashboard view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.batch_worker: Optional[BatchWorker] = None
        self.single_worker: Optional[SingleWorker] = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # =====================================================================
        # LEFT COLUMN: Scrollable Automation Controller
        # =====================================================================
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(12)

        # Header Title
        title_box = QFrame()
        title_box.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 10px;")
        t_layout = QVBoxLayout(title_box)
        t_layout.setSpacing(4)
        lbl_main = QLabel("⚡ OS-Level Auto Profile & Login Engine")
        lbl_main.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        lbl_sub = QLabel(
            "List mein jitni bhi IDs dalein: Har ID ki dedicated profile <b>khud ba khud banegi</b>, "
            "native Firefox chalega, aur OS-level par automatic typing hogi."
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("font-size: 12px; color: #e2e8f0;")
        t_layout.addWidget(lbl_main)
        t_layout.addWidget(lbl_sub)
        left_layout.addWidget(title_box)

        # Dual Mode Tabs: Batch vs Single
        self.mode_tabs = QTabWidget()
        self.mode_tabs.setStyleSheet("""
            QTabBar::tab {
                background: #1e1e24; color: #cbd5e1; padding: 8px 16px; font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #0284c7; color: #ffffff;
            }
        """)

        # Tab 1: Batch List (Multi-Account Auto-Profile & Login)
        batch_widget = self._create_batch_tab()
        self.mode_tabs.addTab(batch_widget, "📋 Batch Accounts List (Auto-Profiles)")

        # Tab 2: Single Account Quick Run
        single_widget = self._create_single_tab()
        self.mode_tabs.addTab(single_widget, "👤 Single Account")

        left_layout.addWidget(self.mode_tabs)
        left_layout.addStretch()

        scroll_area.setWidget(left_container)
        main_layout.addWidget(scroll_area, stretch=5)

        # =====================================================================
        # RIGHT COLUMN: Live Terminal Output Console
        # =====================================================================
        right_frame = QFrame()
        right_frame.setStyleSheet("background-color: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 12px;")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setSpacing(10)

        # Terminal Header
        term_bar = QHBoxLayout()
        term_title = QLabel("📟 Live Execution Terminal Console")
        term_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #4ade80;")
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setStyleSheet("background-color: #334155; color: #f8fafc; padding: 4px 12px; font-weight: bold;")
        self.btn_clear.clicked.connect(self._clear_console)
        term_bar.addWidget(term_title)
        term_bar.addStretch()
        term_bar.addWidget(self.btn_clear)
        right_layout.addLayout(term_bar)

        # Batch Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #334155; border-radius: 4px; text-align: center; color: white; background-color: #1e293b; height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0284c7; border-radius: 3px;
            }
        """)
        right_layout.addWidget(self.progress_bar)

        # Terminal Text Area
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("""
            background-color: #020617;
            color: #86efac;
            font-family: Consolas, 'Courier New', monospace;
            font-size: 12px;
            border: 1px solid #1e293b;
            border-radius: 4px;
            padding: 8px;
        """)
        right_layout.addWidget(self.console, stretch=1)

        # Footer Notice
        notice_box = QLabel(
            "<b>Untouched Browser Execution:</b> Zero WebDrivers, Zero Selenium, Zero Playwright hooks.<br>"
            "Firefox executes as an authentic local application. Keystrokes are sent via Windows OS input events."
        )
        notice_box.setWordWrap(True)
        notice_box.setStyleSheet("background-color: #1e293b; color: #94a3b8; font-size: 11px; padding: 8px; border-radius: 4px;")
        right_layout.addWidget(notice_box)

        main_layout.addWidget(right_frame, stretch=6)

    def _create_batch_tab(self) -> QWidget:
        """Create the batch accounts auto-profile tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)

        lbl = QLabel("Paste account list below (Format: <b>UID:Password</b> or <b>Email:Password</b>, one per line):")
        lbl.setStyleSheet("color: #f8fafc; font-weight: bold; font-size: 12px;")
        layout.addWidget(lbl)

        self.batch_text = QTextEdit()
        # Placeholder shows the FORMAT only - never a real or
        # example password value. Type your own accounts here.
        self.batch_text.setPlaceholderText(
            "Example format (type your own accounts, one per line):\n"
            "<uid-or-email>:<password>\n"
            "<uid-or-email>|<password>\n"
        )
        self.batch_text.setMinimumHeight(150)
        self.batch_text.setStyleSheet("""
            background-color: #1e293b;
            color: #ffffff;
            font-family: Consolas, monospace;
            font-size: 13px;
            border: 1px solid #475569;
            border-radius: 4px;
            padding: 8px;
        """)
        layout.addWidget(self.batch_text)

        # Timing controls
        timing_layout = QHBoxLayout()
        timing_layout.addWidget(QLabel("Page Load Wait:"))
        self.batch_page_delay = QSpinBox()
        self.batch_page_delay.setRange(2, 30)
        self.batch_page_delay.setValue(6)
        self.batch_page_delay.setSuffix(" sec")
        self.batch_page_delay.setStyleSheet("background-color: #1e293b; color: #ffffff; padding: 4px;")
        timing_layout.addWidget(self.batch_page_delay)

        timing_layout.addWidget(QLabel("Pause Between Accounts:"))
        self.batch_pause_delay = QSpinBox()
        self.batch_pause_delay.setRange(1, 60)
        self.batch_pause_delay.setValue(4)
        self.batch_pause_delay.setSuffix(" sec")
        self.batch_pause_delay.setStyleSheet("background-color: #1e293b; color: #ffffff; padding: 4px;")
        timing_layout.addWidget(self.batch_pause_delay)
        layout.addLayout(timing_layout)

        # Big Run Button
        self.btn_run_batch = QPushButton("🚀 Start Batch Auto-Profile & Login")
        self.btn_run_batch.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_run_batch.clicked.connect(self._start_batch_automation)
        layout.addWidget(self.btn_run_batch)

        return widget

    def _create_single_tab(self) -> QWidget:
        """Create single account quick login tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Select Existing Firefox Profile:"))
        self.single_profile_combo = QComboBox()
        self.single_profile_combo.setStyleSheet("background-color: #1e293b; color: #ffffff; padding: 6px; border: 1px solid #475569;")
        self.reload_profiles()
        layout.addWidget(self.single_profile_combo)

        layout.addWidget(QLabel("Facebook UID / Email / Phone:"))
        self.single_uid_input = QLineEdit()
        self.single_uid_input.setPlaceholderText("Enter UID or Email")
        self.single_uid_input.setStyleSheet("background-color: #1e293b; color: #ffffff; padding: 8px; border: 1px solid #475569;")
        layout.addWidget(self.single_uid_input)

        layout.addWidget(QLabel("Facebook Password:"))
        self.single_pass_input = QLineEdit()
        self.single_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.single_pass_input.setPlaceholderText("Enter Password")
        self.single_pass_input.setStyleSheet("background-color: #1e293b; color: #ffffff; padding: 8px; border: 1px solid #475569;")
        layout.addWidget(self.single_pass_input)

        self.chk_single_show = QCheckBox("Show password text")
        self.chk_single_show.setStyleSheet("color: #e2e8f0;")
        self.chk_single_show.toggled.connect(
            lambda chk: self.single_pass_input.setEchoMode(QLineEdit.EchoMode.Normal if chk else QLineEdit.EchoMode.Password)
        )
        layout.addWidget(self.chk_single_show)

        self.btn_run_single = QPushButton("▶ Launch & Login Single Account")
        self.btn_run_single.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 10px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_run_single.clicked.connect(self._start_single_automation)
        layout.addWidget(self.btn_run_single)

        self.btn_type_now = QPushButton("⌨ Type Into Focused Window Now (Instant)")
        self.btn_type_now.setStyleSheet("""
            QPushButton {
                background-color: #475569;
                color: #ffffff;
                font-weight: bold;
                padding: 8px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)
        self.btn_type_now.clicked.connect(self._type_now_into_window)
        layout.addWidget(self.btn_type_now)

        layout.addStretch()
        return widget

    def reload_profiles(self):
        """Update profile combobox in single tab."""
        if not hasattr(self, "single_profile_combo"):
            return
        current = self.single_profile_combo.currentData()
        self.single_profile_combo.clear()
        profiles = orchestrator.profile_agent.list_profiles()
        for p in profiles:
            self.single_profile_combo.addItem(f"{p.name} ({p.id[:8]}...)", p.id)
        if current:
            idx = self.single_profile_combo.findData(current)
            if idx >= 0:
                self.single_profile_combo.setCurrentIndex(idx)

    def _clear_console(self):
        self.console.clear()
        self.progress_bar.setValue(0)

    def log_to_console(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.console.append(f"[{ts}] {msg}")

    # =========================================================================
    # Batch Run Logic
    # =========================================================================

    def _start_batch_automation(self):
        raw_text = self.batch_text.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "List Required", "Please enter at least one account in format UID:Password.")
            return

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            QMessageBox.warning(self, "List Required", "No accounts detected.")
            return

        self.btn_run_batch.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_to_console(f"Starting batch runner for {len(lines)} accounts...")

        self.batch_worker = BatchWorker(
            account_lines=lines,
            page_delay=self.batch_page_delay.value(),
            pause_delay=self.batch_pause_delay.value(),
        )
        self.batch_worker.log_signal.connect(self.log_to_console)
        self.batch_worker.progress_signal.connect(self._on_batch_progress)
        self.batch_worker.finished_signal.connect(self._on_batch_finished)
        self.batch_worker.start()

    def _on_batch_progress(self, current: int, total: int):
        pct = int((current / total) * 100)
        self.progress_bar.setValue(pct)

    def _on_batch_finished(self, success: bool, message: str):
        self.btn_run_batch.setEnabled(True)
        self.progress_bar.setValue(100 if success else 0)
        self.reload_profiles()
        if success:
            self.log_to_console(f"🎉 {message}")
            QMessageBox.information(
                self,
                "Batch Completed",
                f"Batch automation finished!\n\n{message}\n\nAll profiles have been automatically created and saved."
            )
        else:
            self.log_to_console(f"❌ {message}")
            QMessageBox.critical(self, "Batch Error", message)

    # =========================================================================
    # Single Run Logic
    # =========================================================================

    def _start_single_automation(self):
        profile_id = self.single_profile_combo.currentData()
        uid = self.single_uid_input.text().strip()
        pwd = self.single_pass_input.text()

        if not profile_id or not uid or not pwd:
            QMessageBox.warning(self, "Input Required", "Please select a profile, enter UID, and enter Password.")
            return

        self.btn_run_single.setEnabled(False)
        self.log_to_console(f"Starting single automation for {uid}...")

        self.single_worker = SingleWorker(profile_id=profile_id, uid=uid, password=pwd, delay=6)
        self.single_worker.log_signal.connect(self.log_to_console)
        self.single_worker.finished_signal.connect(self._on_single_finished)
        self.single_worker.start()

    def _on_single_finished(self, success: bool, message: str):
        self.btn_run_single.setEnabled(True)
        if success:
            self.log_to_console(f"✓ {message}")
            QMessageBox.information(self, "Single Run Done", "Login keystrokes submitted into native Firefox!")
        else:
            self.log_to_console(f"❌ {message}")
            QMessageBox.critical(self, "Error", message)

    def _type_now_into_window(self):
        uid = self.single_uid_input.text().strip()
        pwd = self.single_pass_input.text()
        if not uid or not pwd:
            QMessageBox.warning(self, "Input Required", "Please enter UID and Password first.")
            return

        self.log_to_console("Waiting 2s... Please click inside the active Facebook input field now!")
        import time
        time.sleep(2.0)
        system_automation.paste_into_focused_input(uid)
        time.sleep(0.3)
        system_automation.send_key(0x09)  # Tab
        time.sleep(0.3)
        system_automation.paste_into_focused_input(pwd)
        time.sleep(0.3)
        system_automation.send_key(0x0D)  # Enter
        self.log_to_console("✓ Typed credentials into active window.")
