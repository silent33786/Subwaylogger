"""
Enterprise GUI Dashboard for Firefox Multi-Profile Management.
Modern desktop interface powered by PySide6. Coordinates real-time metric cards,
profile and account tables, human-in-the-loop verification notifications, and live audit streams.
"""

import sys
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QFrame,
    QStatusBar,
    QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QBrush, QIcon

from firefox_manager.config.settings import settings
from firefox_manager.core.orchestrator import orchestrator
from firefox_manager.database.database import db
from firefox_manager.database.models import AuditSeverity
from firefox_manager.gui.profile_view import ProfileView
from firefox_manager.gui.account_view import AccountView
from firefox_manager.gui.automation_view import AutomationView
from firefox_manager.gui.auto_ads_view import AutoAdsView


DARK_STYLE_SHEET = """
QMainWindow, QWidget {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 13px;
}
QLabel {
    color: #f8fafc;
}
QTabWidget::pane {
    border: 1px solid #1e293b;
    background-color: #0f172a;
    border-radius: 6px;
}
QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    padding: 9px 18px;
    margin-right: 3px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #0284c7;
    color: #ffffff;
    font-weight: bold;
}
QTableWidget {
    background-color: #1e293b;
    gridline-color: #334155;
    border: 1px solid #334155;
    border-radius: 6px;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
    color: #f8fafc;
}
QHeaderView::section {
    background-color: #0f172a;
    color: #38bdf8;
    padding: 7px;
    border: 1px solid #334155;
    font-weight: bold;
}
QPushButton {
    background-color: #334155;
    color: #ffffff;
    border: none;
    padding: 7px 15px;
    border-radius: 5px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #475569;
}
QPushButton:pressed {
    background-color: #0284c7;
}
QLineEdit, QTextEdit, QComboBox {
    background-color: #1e293b;
    color: #ffffff;
    border: 1px solid #475569;
    padding: 7px;
    border-radius: 5px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #38bdf8;
}
QCheckBox {
    color: #f8fafc;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #475569;
    background-color: #1e293b;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background-color: #0284c7;
}
QSpinBox {
    background-color: #1e293b;
    color: #ffffff;
    border: 1px solid #475569;
    padding: 5px;
    border-radius: 4px;
}
"""


class MetricCard(QFrame):
    """Modern dashboard summary card."""

    def __init__(self, title: str, initial_value: str = "0", color: str = "#007acc"):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"MetricCard {{ background-color: #252526; border-left: 4px solid {color}; border-radius: 6px; padding: 8px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        self.lbl_val = QLabel(initial_value)
        self.lbl_val.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: bold;")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_val)

    def set_value(self, val: str):
        self.lbl_val.setText(val)


class DashboardWindow(QMainWindow):
    """Main desktop control center."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{settings.app_name} v{settings.app_version}")
        self.resize(1150, 750)
        self.setStyleSheet(DARK_STYLE_SHEET)

        # Initialize orchestrator subsystem
        orchestrator.initialize()

        self._setup_ui()
        self._setup_timer()
        self._refresh_all()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # Verification Alert Banner (hidden by default)
        self.alert_banner = QFrame()
        self.alert_banner.setStyleSheet(
            "background-color: #d32f2f; color: white; border-radius: 6px; padding: 6px 12px;"
        )
        banner_layout = QHBoxLayout(self.alert_banner)
        self.lbl_alert_msg = QLabel("⚠ Security verification required! Automation paused for safety.")
        self.lbl_alert_msg.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.btn_focus_window = QPushButton("🔍 Bring Firefox to Front")
        self.btn_focus_window.setStyleSheet("background-color: #ffffff; color: #d32f2f; font-weight: bold;")
        self.btn_focus_window.clicked.connect(self._focus_verification_window)

        self.btn_resolve_challenge = QPushButton("✓ Completed Verification")
        self.btn_resolve_challenge.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.btn_resolve_challenge.clicked.connect(self._resolve_verification_challenge)

        banner_layout.addWidget(self.lbl_alert_msg)
        banner_layout.addStretch()
        banner_layout.addWidget(self.btn_focus_window)
        banner_layout.addWidget(self.btn_resolve_challenge)
        self.alert_banner.setVisible(False)
        main_layout.addWidget(self.alert_banner)

        # Top Metric Cards Grid
        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(10)
        self.card_total = MetricCard("Total Profiles", "0", "#007acc")
        self.card_active = MetricCard("Active Profiles", "0", "#4caf50")
        self.card_inactive = MetricCard("Inactive Profiles", "0", "#757575")
        self.card_accounts = MetricCard("Connected Accounts", "0", "#ab47bc")
        self.card_resources = MetricCard("Process CPU / RAM", "0% / 0 MB", "#ff9800")

        metrics_layout.addWidget(self.card_total, 0, 0)
        metrics_layout.addWidget(self.card_active, 0, 1)
        metrics_layout.addWidget(self.card_inactive, 0, 2)
        metrics_layout.addWidget(self.card_accounts, 0, 3)
        metrics_layout.addWidget(self.card_resources, 0, 4)
        main_layout.addLayout(metrics_layout)

        # Tab Widget
        self.tabs = QTabWidget()
        self.profile_view = ProfileView()
        self.automation_view = AutomationView()
        self.auto_ads_view = AutoAdsView()
        self.account_view = AccountView()
        self.log_table = self._create_log_widget()
        self.system_view = self._create_system_widget()

        self.tabs.addTab(self.profile_view, "🌐 Firefox Profiles")
        self.tabs.addTab(self.automation_view, "⚡ OS Automation")
        self.tabs.addTab(self.auto_ads_view, "📢 Auto Ads")
        self.tabs.addTab(self.account_view, "👤 Account Management")
        self.tabs.addTab(self.log_table, "📋 Audit & Activity Logs")
        self.tabs.addTab(self.system_view, "⚙ System & Recovery")
        main_layout.addWidget(self.tabs)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Engine ready. Native Firefox Multi-Profile Active.")

    def _create_log_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # Top toolbar
        toolbar = QHBoxLayout()
        btn_refresh_logs = QPushButton("⟳ Refresh Logs")
        btn_refresh_logs.clicked.connect(self._reload_logs)
        toolbar.addStretch()
        toolbar.addWidget(btn_refresh_logs)
        layout.addLayout(toolbar)

        self.table_logs = QTableWidget()
        self.table_logs.setColumnCount(5)
        self.table_logs.setHorizontalHeaderLabels(["Timestamp", "Severity", "Agent", "Action", "Details"])
        self.table_logs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_logs.horizontalHeader().setStretchLastSection(True)
        self.table_logs.setAlternatingRowColors(True)
        layout.addWidget(self.table_logs)
        return widget

    def _create_system_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        lbl_header = QLabel("System Maintenance & Reliability Controls")
        lbl_header.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(lbl_header)

        btn_backup = QPushButton("💾 Backup Database Snapshot Now")
        btn_backup.setStyleSheet("background-color: #007acc; color: white; padding: 10px; font-weight: bold;")
        btn_backup.clicked.connect(self._trigger_db_backup)
        layout.addWidget(btn_backup)

        btn_locks = QPushButton("🧹 Clear Stale Firefox Locks (parent.lock)")
        btn_locks.setStyleSheet("background-color: #f57c00; color: white; padding: 10px; font-weight: bold;")
        btn_locks.clicked.connect(self._trigger_clear_locks)
        layout.addWidget(btn_locks)

        btn_purge_junk = QPushButton("🗑 Wipe All Orphaned / Junk Profile Folders From Disk")
        btn_purge_junk.setStyleSheet("background-color: #c62828; color: white; padding: 10px; font-weight: bold;")
        btn_purge_junk.clicked.connect(self._trigger_purge_junk)
        layout.addWidget(btn_purge_junk)

        btn_audit = QPushButton("🔒 Run Profile Filesystem Isolation Audit")
        btn_audit.setStyleSheet("background-color: #2e7d32; color: white; padding: 10px; font-weight: bold;")
        btn_audit.clicked.connect(self._trigger_isolation_audit)
        layout.addWidget(btn_audit)

        btn_scan = QPushButton("🔍 Scan System for Deleted Profiles & Leftover Junk")
        btn_scan.setStyleSheet("background-color: #6d28d9; color: white; padding: 10px; font-weight: bold;")
        btn_scan.clicked.connect(self._trigger_system_scan)
        layout.addWidget(btn_scan)

        layout.addStretch()
        return widget

    def _setup_timer(self):
        """Timer to periodically poll metrics, logs, and verification requests."""
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self._on_heartbeat)
        self.timer.start()

    def _on_heartbeat(self):
        """Periodic background refresh."""
        summary = orchestrator.get_dashboard_summary()
        self.card_total.set_value(str(summary["total_profiles"]))
        self.card_active.set_value(str(summary["active_profiles"]))
        self.card_inactive.set_value(str(summary["inactive_profiles"]))
        self.card_accounts.set_value(str(summary["connected_accounts"]))
        self.card_resources.set_value(
            f"{summary['total_cpu_percent']}% / {summary['total_memory_mb']} MB"
        )

        # Check pending human verifications
        pending = orchestrator.verification_handler.get_pending_requests()
        if pending:
            req = pending[0]
            self.lbl_alert_msg.setText(
                f"⚠ Verification Required on Profile: {req.profile_id[:8]}... Challenge: '{req.challenge_type}'"
            )
            self.alert_banner.setVisible(True)
        else:
            self.alert_banner.setVisible(False)

    def _refresh_all(self):
        self._on_heartbeat()
        self.profile_view.reload_data()
        self.automation_view.reload_profiles()
        self.auto_ads_view.reload_profiles()
        self.account_view.reload_data()
        self._reload_logs()

    def _reload_logs(self):
        logs = db.get_recent_audit_logs(limit=100)
        self.table_logs.setRowCount(len(logs))
        for row, l in enumerate(logs):
            time_str = l.timestamp[:19].replace("T", " ")
            self.table_logs.setItem(row, 0, QTableWidgetItem(time_str))

            sev_item = QTableWidgetItem(l.severity.value)
            if l.severity == AuditSeverity.ERROR or l.severity == AuditSeverity.CRITICAL:
                sev_item.setForeground(QBrush(QColor("#f44336")))
            elif l.severity == AuditSeverity.WARNING:
                sev_item.setForeground(QBrush(QColor("#ff9800")))
            else:
                sev_item.setForeground(QBrush(QColor("#90caf9")))
            self.table_logs.setItem(row, 1, sev_item)

            self.table_logs.setItem(row, 2, QTableWidgetItem(l.agent_name))
            self.table_logs.setItem(row, 3, QTableWidgetItem(l.action))
            self.table_logs.setItem(row, 4, QTableWidgetItem(l.details or ""))

    def _focus_verification_window(self):
        pending = orchestrator.verification_handler.get_pending_requests()
        if pending:
            orchestrator.process_manager.bring_to_front(pending[0].profile_id)

    def _resolve_verification_challenge(self):
        pending = orchestrator.verification_handler.get_pending_requests()
        if not pending:
            return
        req = pending[0]
        reply = QMessageBox.question(
            self,
            "Confirm Verification",
            "Have you successfully solved the security verification challenge in Firefox?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            orchestrator.verification_handler.resolve_verification(req.request_id, success=True)
            self.account_view.reload_data()
            self._on_heartbeat()

    def _trigger_db_backup(self):
        backup_path = orchestrator.recovery_agent.backup_database()
        if backup_path:
            QMessageBox.information(self, "Backup Complete", f"Snapshot created at:\n{backup_path}")
        else:
            QMessageBox.critical(self, "Backup Failed", "Failed to create database backup snapshot.")

    def _trigger_clear_locks(self):
        cleaned = orchestrator.recovery_agent.clean_all_stale_locks()
        QMessageBox.information(self, "Lock Cleanup", f"Cleared {cleaned} orphaned profile lock(s).")

    def _trigger_purge_junk(self):
        from firefox_manager.core.profile_manager import profile_manager
        count = profile_manager.clean_orphaned_profiles()
        self.profile_view.reload_data()
        self._on_heartbeat()
        QMessageBox.information(
            self,
            "Junk Profile Cleanup",
            f"Wiped {count} unmapped / orphaned profile folder(s) from your hard drive.\n"
            "Zero residual junk remains on the system.",
        )

    def _trigger_isolation_audit(self):
        results = orchestrator.security_agent.audit_all_profiles()
        summary = "\n".join([f"• {name}: {'Isolated (Safe)' if ok else 'WARNING: Risk detected'}" for name, ok in results.items()])
        QMessageBox.information(
            self, "Security Isolation Audit",
            f"Audit completed across {len(results)} profiles:\n\n{summary or 'No profiles registered yet.'}"
        )

    def _trigger_system_scan(self):
        from firefox_manager.security.system_scanner import system_scanner
        rep = system_scanner.run_full_system_scan()
        msg = f"{rep['summary']}\n\n"
        msg += f"• Active Profiles Managed: {', '.join(rep['registered_profiles']) or 'None'}\n"
        msg += f"• Disk Profile Folders: {', '.join(rep['disk_folders']) or 'None'}\n"
        msg += f"• Orphaned Junk Folders: {', '.join(rep['orphaned_folders']) or 'Zero (Clean)'}\n"
        msg += f"• Temp Artifacts: {', '.join(rep['temp_artifacts']) or 'Zero (Clean)'}\n"
        QMessageBox.information(self, "System Scan & Deletion Audit", msg)

    def closeEvent(self, event):
        """Handle application close gracefully."""
        orchestrator.shutdown()
        event.accept()

