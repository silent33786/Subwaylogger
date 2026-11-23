"""
Profile Management View for PySide6 Dashboard.
Provides table listing, status indicators, and actions: Create, Launch, Stop, Restart, Delete.
"""

from typing import Optional, List
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QLabel,
    QLineEdit,
    QTextEdit,
    QMessageBox,
    QDialogButtonBox,
    QFormLayout,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush

from firefox_manager.core.orchestrator import orchestrator
from firefox_manager.database.models import ProfileRecord, ProfileStatus
from firefox_manager.browser.profile_packager import profile_packager


class CreateProfileDialog(QDialog):
    """Dialog for creating a new independent Firefox profile."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Firefox Profile")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Work_Profile_1")
        layout.addRow("Profile Name *:", self.name_input)

        self.user_agent_input = QLineEdit()
        self.user_agent_input.setPlaceholderText("Leave blank for native default")
        layout.addRow("Custom User Agent:", self.user_agent_input)

        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("e.g. 127.0.0.1:8080 or socks5://127.0.0.1:1080")
        layout.addRow("Proxy Server:", self.proxy_input)

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("e.g. finance, personal (comma separated)")
        layout.addRow("Tags:", self.tags_input)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Optional notes or description...")
        self.notes_input.setMaximumHeight(80)
        layout.addRow("Notes:", self.notes_input)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

    def _validate_and_accept(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Profile Name is required.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "custom_user_agent": self.user_agent_input.text().strip() or None,
            "proxy_server": self.proxy_input.text().strip() or None,
            "tags": self.tags_input.text().strip(),
            "notes": self.notes_input.toPlainText().strip(),
        }


class ProfileView(QWidget):
    """Profile management tab."""

    profile_action_requested = Signal(str, str)  # action, profile_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_create = QPushButton("➕ Create Profile")
        self.btn_create.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_create.clicked.connect(self._open_create_dialog)

        self.btn_launch = QPushButton("▶ Launch")
        self.btn_launch.setStyleSheet("background-color: #1976d2; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_launch.clicked.connect(lambda: self._trigger_selected("launch"))

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setStyleSheet("background-color: #d32f2f; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_stop.clicked.connect(lambda: self._trigger_selected("stop"))

        self.btn_restart = QPushButton("🔄 Restart")
        self.btn_restart.setStyleSheet("background-color: #f57c00; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_restart.clicked.connect(lambda: self._trigger_selected("restart"))

        self.btn_delete = QPushButton("🗑 Delete")
        self.btn_delete.setStyleSheet("background-color: #424242; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_delete.clicked.connect(lambda: self._trigger_selected("delete"))

        self.btn_export = QPushButton("📦 Export (.zip)")
        self.btn_export.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_export.setToolTip("Export profile to a portable .zip to send to another PC")
        self.btn_export.clicked.connect(self._export_selected_profile)

        self.btn_import = QPushButton("📥 Import Profile")
        self.btn_import.setStyleSheet("background-color: #0d9488; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_import.setToolTip("Import a profile bundle from another PC")
        self.btn_import.clicked.connect(self._import_profile)

        self.btn_native_ff = QPushButton("🌐 Native Firefox")
        self.btn_native_ff.setStyleSheet("background-color: #7c3aed; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_native_ff.setToolTip("Launch selected profile directly using Windows default Firefox")
        self.btn_native_ff.clicked.connect(lambda: self._trigger_selected("launch_native"))

        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.clicked.connect(self.reload_data)

        toolbar.addWidget(self.btn_create)
        toolbar.addWidget(self.btn_launch)
        toolbar.addWidget(self.btn_stop)
        toolbar.addWidget(self.btn_restart)
        toolbar.addWidget(self.btn_delete)
        toolbar.addWidget(self.btn_export)
        toolbar.addWidget(self.btn_import)
        toolbar.addWidget(self.btn_native_ff)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_refresh)
        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Profile Name", "Status", "PID", "Disk Usage", "Tags", "Last Launched"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

    def reload_data(self):
        """Refresh profile records from database."""
        profiles = orchestrator.profile_agent.list_profiles()
        self.table.setRowCount(len(profiles))

        for row, p in enumerate(profiles):
            self.table.setItem(row, 0, QTableWidgetItem(p.id[:8] + "..."))
            self.table.setItem(row, 1, QTableWidgetItem(p.name))

            # Status pill item
            status_item = QTableWidgetItem(p.status.value.upper())
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if p.status == ProfileStatus.RUNNING:
                status_item.setForeground(QBrush(QColor("#4caf50")))
            elif p.status == ProfileStatus.ERROR:
                status_item.setForeground(QBrush(QColor("#f44336")))
            elif p.status in (ProfileStatus.STARTING, ProfileStatus.RESTARTING):
                status_item.setForeground(QBrush(QColor("#ff9800")))
            else:
                status_item.setForeground(QBrush(QColor("#9e9e9e")))
            self.table.setItem(row, 2, status_item)

            # PID
            pid_str = str(p.pid) if p.pid else "-"
            self.table.setItem(row, 3, QTableWidgetItem(pid_str))

            # Disk usage
            kb = p.disk_usage_bytes / 1024
            mb = kb / 1024
            size_str = f"{mb:.1f} MB" if mb >= 1 else f"{kb:.0f} KB"
            self.table.setItem(row, 4, QTableWidgetItem(size_str))

            # Tags
            self.table.setItem(row, 5, QTableWidgetItem(p.tags or "-"))

            # Last launched
            launched_str = p.last_launched_at[:19].replace("T", " ") if p.last_launched_at else "Never"
            self.table.setItem(row, 6, QTableWidgetItem(launched_str))

            # Store full ID in UserRole of column 0
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, p.id)

    def _get_selected_profile_id(self) -> Optional[str]:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole)

    def _trigger_selected(self, action: str):
        profile_id = self._get_selected_profile_id()
        if not profile_id:
            QMessageBox.information(self, "Selection Required", "Please select a profile from the table.")
            return

        try:
            if action == "launch":
                orchestrator.profile_agent.launch_profile(profile_id)
            elif action == "stop":
                orchestrator.profile_agent.stop_profile(profile_id)
            elif action == "restart":
                orchestrator.profile_agent.restart_profile(profile_id)
            elif action == "launch_native":
                selected_profile = orchestrator.profile_agent.get_profile(profile_id)
                if selected_profile:
                    import subprocess
                    from firefox_manager.config.settings import settings
                    firefox_bin = str(settings.firefox_binary or r"C:\Program Files\Mozilla Firefox\firefox.exe")
                    subprocess.Popen([firefox_bin, "-P", selected_profile.name])
                    QMessageBox.information(
                        self,
                        "Launched in Native Firefox",
                        f"Profile '{selected_profile.name}' launched directly using Windows default Firefox binary.",
                    )
            elif action == "delete":
                selected_profile = orchestrator.profile_agent.get_profile(profile_id)
                prof_name = selected_profile.name if selected_profile else "Selected Profile"
                reply = QMessageBox.question(
                    self,
                    "Confirm Permanent Deletion",
                    f"Are you sure you want to PERMANENTLY delete profile '{prof_name}'?\n\n"
                    "This action cannot be undone and will completely remove all its data, cookies, and files from your system.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    success = orchestrator.profile_agent.delete_profile(profile_id, remove_disk_files=True)
                    self.reload_data()
                    if success:
                        QMessageBox.information(
                            self,
                            "Profile Permanently Deleted",
                            f"Profile '{prof_name}' and all its files on disk have been completely removed from your computer.",
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            "Deletion Warning",
                            f"Profile '{prof_name}' database record removed, but some files on disk may have been locked. Please check the profiles folder.",
                        )
            self.reload_data()
        except Exception as e:
            QMessageBox.critical(self, "Operation Error", str(e))

    def _open_create_dialog(self):
        dialog = CreateProfileDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                orchestrator.profile_agent.create_profile(
                    name=data["name"],
                    custom_user_agent=data["custom_user_agent"],
                    proxy_server=data["proxy_server"],
                    tags=data["tags"],
                    notes=data["notes"],
                )
                self.reload_data()
                QMessageBox.information(self, "Success", f"Profile '{data['name']}' created successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Creation Error", str(e))

    def _export_selected_profile(self):
        """Export selected profile to a portable .zip package for another PC."""
        profile_id = self._get_selected_profile_id()
        if not profile_id:
            QMessageBox.information(self, "Selection Required", "Please select a profile to export.")
            return

        selected_profile = orchestrator.profile_agent.get_profile(profile_id)
        if not selected_profile:
            return

        dest_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Portable Profile Package",
            f"{selected_profile.name}_portable.zip",
            "Zip Archive (*.zip)",
        )
        if not dest_file:
            return

        try:
            zip_path = profile_packager.export_profile_bundle(profile_id, Path(dest_file))
            QMessageBox.information(
                self,
                "Profile Exported Successfully",
                f"Profile '{selected_profile.name}' has been exported to:\n{zip_path}\n\n"
                "Aap is zip file ko kisi bhi dosray computer par le ja kar 'Import Profile' "
                "ke zariye baghair kisi data loss ke direct run kar sakte hain!",
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _import_profile(self):
        """Import a profile package (.zip or directory) from another PC."""
        src_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Portable Profile Package",
            "",
            "Profile Archives (*.zip);;All Files (*.*)",
        )
        if not src_file:
            return

        try:
            rec = profile_packager.import_profile_bundle(Path(src_file))
            self.reload_data()
            QMessageBox.information(
                self,
                "Profile Imported Successfully",
                f"Profile '{rec.name}' has been successfully imported!\n"
                "All cookies, logins, and configurations are intact and ready to launch.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", str(e))

