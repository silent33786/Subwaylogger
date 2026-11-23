"""
Account Management View for PySide6 Dashboard.
Manages authorized accounts, profile mappings, status tracking,
and initiates manual human authentication flows.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QMessageBox,
    QDialogButtonBox,
    QFormLayout,
    QCheckBox,
    QSpinBox,
    QLabel,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QBrush

from firefox_manager.core.orchestrator import orchestrator
from firefox_manager.database.models import AccountRecord, AccountStatus
from firefox_manager.authentication.system_automation import system_automation


class FacebookLoginWorker(QThread):
    """Background worker executing native OS-level Facebook automation."""

    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, profile_id: str, uid: str, password: str, delay: int, save_vault: bool):
        super().__init__()
        self.profile_id = profile_id
        self.uid = uid
        self.password = password
        self.delay = delay
        self.save_vault = save_vault

    def run(self):
        try:
            result = system_automation.run_facebook_login_system_level(
                profile_id=self.profile_id,
                username_or_uid=self.uid,
                password=self.password,
                page_load_delay=float(self.delay),
                status_callback=lambda msg: self.log_signal.emit(msg),
                save_to_vault=self.save_vault,
            )
            self.finished_signal.emit(result.get("success", False), result.get("message", "Completed"))
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class FacebookAutoLoginDialog(QDialog):
    """Dashboard dialog for native OS-level Facebook login automation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚡ Facebook Native System-Level Auto-Login")
        self.setMinimumWidth(520)
        self.worker: Optional[FacebookLoginWorker] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info_lbl = QLabel(
            "<b>Pure Native OS Automation</b>: Browser remains 100% untouched.<br>"
            "Firefox launches natively and credentials are typed directly via Windows keyboard events."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #90caf9; padding: 6px; background-color: #1e2a38; border-radius: 4px;")
        layout.addWidget(info_lbl)

        form = QFormLayout()
        form.setSpacing(10)

        # Profile selection
        self.profile_combo = QComboBox()
        profiles = orchestrator.profile_agent.list_profiles()
        for p in profiles:
            self.profile_combo.addItem(f"{p.name} (Dir: {p.directory_name})", p.id)
        form.addRow("Firefox Profile *:", self.profile_combo)

        # FB UID / Username / Email
        self.uid_input = QLineEdit()
        self.uid_input.setPlaceholderText("Enter Facebook UID, Email, or Phone")
        form.addRow("Facebook UID / Email *:", self.uid_input)

        # FB Password
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setPlaceholderText("Enter Facebook Password")
        form.addRow("Facebook Password *:", self.pass_input)

        # Show password toggle
        self.chk_show_pass = QCheckBox("Show Password")
        self.chk_show_pass.toggled.connect(
            lambda checked: self.pass_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        form.addRow("", self.chk_show_pass)

        # Page load delay
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(2, 30)
        self.delay_spin.setValue(6)
        self.delay_spin.setSuffix(" seconds")
        form.addRow("Wait for Page Load:", self.delay_spin)

        # Save to vault
        self.chk_vault = QCheckBox("Save credentials securely in Windows Credential Vault")
        self.chk_vault.setChecked(True)
        form.addRow("", self.chk_vault)

        layout.addLayout(form)

        # Live status log area
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setPlaceholderText("Live automation progress will appear here...")
        self.status_box.setMaximumHeight(120)
        self.status_box.setStyleSheet("background-color: #121212; color: #a5d6a7; font-family: Consolas, monospace;")
        layout.addWidget(self.status_box)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("🚀 Start Native FB Login")
        self.btn_start.setStyleSheet("background-color: #1565c0; color: white; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        self.btn_start.clicked.connect(self._start_automation)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _start_automation(self):
        profile_id = self.profile_combo.currentData()
        uid = self.uid_input.text().strip()
        pwd = self.pass_input.text()

        if not profile_id:
            QMessageBox.warning(self, "Validation Error", "Please select or create a Firefox profile first.")
            return

        if not uid or not pwd:
            QMessageBox.warning(self, "Validation Error", "Facebook UID and Password are both required.")
            return

        self.btn_start.setEnabled(False)
        self.status_box.clear()
        self.status_box.append("Starting system-level automation...")

        self.worker = FacebookLoginWorker(
            profile_id=profile_id,
            uid=uid,
            password=pwd,
            delay=self.delay_spin.value(),
            save_vault=self.chk_vault.isChecked(),
        )
        self.worker.log_signal.connect(self._on_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _on_log(self, msg: str):
        self.status_box.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _on_finished(self, success: bool, message: str):
        self.btn_start.setEnabled(True)
        if success:
            self.status_box.append(f"\n[DONE] {message}")
            QMessageBox.information(
                self,
                "Automation Complete",
                "Facebook login submitted successfully at system level!\n\n"
                "Firefox is running in front of you. If Facebook asks for 2FA/SMS code, "
                "please complete it in the browser window."
            )
        else:
            self.status_box.append(f"\n[ERROR] {message}")
            QMessageBox.critical(self, "Automation Error", message)


class AddAccountDialog(QDialog):
    """Dialog for registering an authorized account and linking to a profile."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Authorized Account")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)

        self.service_input = QLineEdit()
        self.service_input.setPlaceholderText("e.g. Google, GitHub, Twitter, Microsoft")
        layout.addRow("Service Name *:", self.service_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username or Handle")
        layout.addRow("Username *:", self.username_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Optional login email")
        layout.addRow("Email:", self.email_input)

        # Profile selection
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("-- None (Unassigned) --", None)
        profiles = orchestrator.profile_agent.list_profiles()
        for p in profiles:
            self.profile_combo.addItem(f"{p.name} ({p.id[:8]}...)", p.id)
        layout.addRow("Dedicated Profile:", self.profile_combo)

        # Password input (encrypted, never saved plaintext)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Stored in secure OS vault (Optional)")
        layout.addRow("Credential Secret:", self.password_input)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Optional account notes...")
        self.notes_input.setMaximumHeight(70)
        layout.addRow("Notes:", self.notes_input)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

    def _validate_and_accept(self):
        service = self.service_input.text().strip()
        user = self.username_input.text().strip()
        if not service or not user:
            QMessageBox.warning(self, "Validation Error", "Service Name and Username are required.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "service_name": self.service_input.text().strip(),
            "username": self.username_input.text().strip(),
            "email": self.email_input.text().strip() or None,
            "profile_id": self.profile_combo.currentData(),
            "password": self.password_input.text() or None,
            "notes": self.notes_input.toPlainText().strip(),
        }


class AccountView(QWidget):
    """Account management tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_fb_auto = QPushButton("⚡ Facebook Auto-Login")
        self.btn_fb_auto.setStyleSheet("background-color: #1565c0; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.btn_fb_auto.clicked.connect(self._open_fb_dialog)

        self.btn_add = QPushButton("➕ Add Account")
        self.btn_add.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_add.clicked.connect(self._open_add_dialog)

        self.btn_manual_login = QPushButton("🔑 Manual Login")
        self.btn_manual_login.setStyleSheet("background-color: #455a64; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_manual_login.clicked.connect(self._trigger_manual_login)

        self.btn_confirm_auth = QPushButton("✓ Mark Authenticated")
        self.btn_confirm_auth.setStyleSheet("background-color: #00796b; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_confirm_auth.clicked.connect(self._trigger_confirm_auth)

        self.btn_delete = QPushButton("🗑 Delete Account")
        self.btn_delete.setStyleSheet("background-color: #424242; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_delete.clicked.connect(self._trigger_delete)

        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.clicked.connect(self.reload_data)

        toolbar.addWidget(self.btn_fb_auto)
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_manual_login)
        toolbar.addWidget(self.btn_confirm_auth)
        toolbar.addWidget(self.btn_delete)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_refresh)
        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Service", "Username / Email", "Mapped Profile", "Status", "Last Login", "Vault Key"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

    def reload_data(self):
        """Refresh account records from database."""
        accounts = orchestrator.account_agent.list_accounts()
        profiles = {p.id: p.name for p in orchestrator.profile_agent.list_profiles()}
        self.table.setRowCount(len(accounts))

        for row, a in enumerate(accounts):
            self.table.setItem(row, 0, QTableWidgetItem(a.id[:8] + "..."))
            self.table.setItem(row, 1, QTableWidgetItem(a.service_name))

            user_str = a.username
            if a.email:
                user_str += f" ({a.email})"
            self.table.setItem(row, 2, QTableWidgetItem(user_str))

            profile_name = profiles.get(a.profile_id, "Unmapped" if not a.profile_id else "Unknown")
            self.table.setItem(row, 3, QTableWidgetItem(profile_name))

            # Status pill
            status_item = QTableWidgetItem(a.status.value.upper().replace("_", " "))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if a.status == AccountStatus.ACTIVE:
                status_item.setForeground(QBrush(QColor("#4caf50")))
            elif a.status == AccountStatus.VERIFICATION_NEEDED:
                status_item.setForeground(QBrush(QColor("#ff9800")))
            elif a.status == AccountStatus.SESSION_EXPIRED:
                status_item.setForeground(QBrush(QColor("#f44336")))
            else:
                status_item.setForeground(QBrush(QColor("#9e9e9e")))
            self.table.setItem(row, 4, status_item)

            last_login_str = a.last_login_at[:19].replace("T", " ") if a.last_login_at else "Never"
            self.table.setItem(row, 5, QTableWidgetItem(last_login_str))

            # Credential check
            has_secret = orchestrator.security_agent.get_credential(a.service_name, a.username) != ""
            self.table.setItem(row, 6, QTableWidgetItem("Protected" if has_secret else "None"))

            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, a.id)

    def _get_selected_account_id(self) -> Optional[str]:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole)

    def _open_fb_dialog(self):
        dialog = FacebookAutoLoginDialog(self)
        dialog.exec()
        self.reload_data()

    def _open_add_dialog(self):
        dialog = AddAccountDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                orchestrator.account_agent.add_account(
                    service_name=data["service_name"],
                    username=data["username"],
                    email=data["email"],
                    profile_id=data["profile_id"],
                    password=data["password"],
                    notes=data["notes"],
                )
                self.reload_data()
                QMessageBox.information(self, "Success", f"Account '{data['username']}' added successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _trigger_manual_login(self):
        acc_id = self._get_selected_account_id()
        if not acc_id:
            QMessageBox.information(self, "Selection Required", "Please select an account from the table.")
            return

        try:
            orchestrator.account_agent.launch_for_manual_auth(acc_id)
            QMessageBox.information(
                self,
                "Manual Login Launched",
                "Firefox has opened with this account's profile.\n\n"
                "Please perform sign-in directly in Firefox, complete any 2FA/security verification, "
                "then click 'Mark Authenticated' once finished."
            )
            self.reload_data()
        except Exception as e:
            QMessageBox.critical(self, "Login Error", str(e))

    def _trigger_confirm_auth(self):
        acc_id = self._get_selected_account_id()
        if not acc_id:
            QMessageBox.information(self, "Selection Required", "Please select an account.")
            return

        try:
            orchestrator.account_agent.confirm_manual_auth(acc_id)
            self.reload_data()
            QMessageBox.information(self, "Status Updated", "Account marked as ACTIVE with updated login timestamp.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _trigger_delete(self):
        acc_id = self._get_selected_account_id()
        if not acc_id:
            QMessageBox.information(self, "Selection Required", "Please select an account.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            "Are you sure you want to delete this account and purge its secure credentials?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            orchestrator.account_agent.delete_account(acc_id)
            self.reload_data()

