"""
PySide6 GUI View for 'Auto Ads' Automation.
Allows the user to select an existing profile, enter all ad parameters up-front,
and run the end-to-end Facebook Pro Mode & Ad Creation automation with zero in-flight prompts.
Features:
- Step-by-step visual execution checklist
- One-click 'Quick Fill Demo Preset' for rapid testing
- Live Session Status badge (Logged in / Logged out detection)
- Complete control bar: Launch, Pause, Resume, and Abort
- Interactive Firefox inspector button
"""

import time
from pathlib import Path
from typing import Optional, List
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
    QDoubleSpinBox,
    QFrame,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

from firefox_manager.database.database import db
from firefox_manager.core.process_manager import process_manager
from firefox_manager.core.profile_manager import profile_manager
from firefox_manager.browser.profile_storage import profile_storage
from firefox_manager.authentication.system_automation import system_automation
from firefox_manager.automation.auto_ads_models import AutoAdsConfig
from firefox_manager.automation.auto_ads_engine import auto_ads_engine
from firefox_manager.automation.profile_logger import profile_logger
from firefox_manager.automation.ad_agent_memory import agent_memory
from firefox_manager.automation.ad_agent_recovery import agent_recovery


STEPS_DESCRIPTIONS = [
    "Profile & Native Firefox Resolution",
    "Profile Lock Inspection & Unlock",
    "Professional Mode Check & Activation",
    "Meta Ad Center Navigation",
    "Ad Objective: Traffic / Website Visitors",
    "Ad Creative: Description, Media, Headline & URL",
    "Audience Targeting, EU Compliance & Budget",
    "Final Review & Publication Submission",
]


class AutoAdsWorker(QThread):
    """Background worker executing the end-to-end Auto Ads workflow."""

    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    finished_signal = Signal(bool, str)

    def __init__(self, config: AutoAdsConfig):
        super().__init__()
        self.config = config

    def run(self):
        try:
            res = auto_ads_engine.run_auto_ads_workflow(
                config=self.config,
                status_callback=lambda msg: self.log_signal.emit(msg),
                progress_callback=lambda cur, tot: self.progress_signal.emit(cur, tot),
            )
            self.finished_signal.emit(True, res.get("message", "Auto Ads completed successfully!"))
        except InterruptedError as ie:
            self.finished_signal.emit(False, str(ie))
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            profile_logger.log(self.config.profile_id, f"❌ FATAL EXECUTION ERROR: {str(e)}\n{tb}")
            self.finished_signal.emit(False, f"{str(e)}")


class AutoAdsView(QWidget):
    """Interactive, user-friendly GUI tab for Facebook Auto Ads creation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: Optional[AutoAdsWorker] = None
        self.step_labels: List[QLabel] = []
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)

        # =====================================================================
        # LEFT COLUMN: Scrollable Form Inputs
        # =====================================================================
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 10, 4)
        layout.setSpacing(12)

        # Header Title Card
        title_box = QFrame()
        title_box.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e293b, stop:1 #0f172a);"
            "border: 1px solid #334155; border-radius: 8px; padding: 12px;"
        )
        t_layout = QVBoxLayout(title_box)
        t_layout.setSpacing(4)
        lbl_main = QLabel("📢 Facebook Auto Ads & Pro Mode Engine")
        lbl_main.setStyleSheet("font-size: 17px; font-weight: bold; color: #38bdf8;")
        lbl_sub = QLabel(
            "Tamam inputs yahan pehle se set karein. Automation ke doran browser khud ba khud Pro Mode activate karega, "
            "Ad Center open karega, aur ad parameters submit karega."
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("font-size: 12px; color: #94a3b8;")
        t_layout.addWidget(lbl_main)
        t_layout.addWidget(lbl_sub)

        # Quick Preset & Actions bar inside header
        preset_bar = QHBoxLayout()
        self.btn_quick_preset = QPushButton("⚡ Quick Fill Demo Preset")
        self.btn_quick_preset.setStyleSheet(
            "background-color: #0369a1; color: #ffffff; padding: 5px 12px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_quick_preset.clicked.connect(self._fill_quick_preset)

        self.btn_open_browser = QPushButton("🔍 Open Selected Profile")
        self.btn_open_browser.setStyleSheet(
            "background-color: #334155; color: #e2e8f0; padding: 5px 12px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_open_browser.clicked.connect(self._open_selected_profile)

        self.btn_open_log = QPushButton("📄 View Profile Log")
        self.btn_open_log.setStyleSheet(
            "background-color: #475569; color: #e2e8f0; padding: 5px 12px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_open_log.setToolTip("Open dedicated log file for this profile in Notepad")
        self.btn_open_log.clicked.connect(self._open_profile_log)

        self.btn_view_memory = QPushButton("🧠 Memory Stats")
        self.btn_view_memory.setStyleSheet(
            "background-color: #581c87; color: #e9d5ff; padding: 5px 12px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_view_memory.setToolTip("Inspect self-learning memory heuristic scores")
        self.btn_view_memory.clicked.connect(self._show_memory_dialog)

        self.btn_open_shots = QPushButton("📸 Screenshots")
        self.btn_open_shots.setStyleSheet(
            "background-color: #1e3a5f; color: #bae6fd; padding: 5px 12px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_open_shots.setToolTip("Open diagnostic screenshots folder")
        self.btn_open_shots.clicked.connect(self._open_screenshots_folder)

        preset_bar.addWidget(self.btn_quick_preset)
        preset_bar.addWidget(self.btn_open_browser)
        preset_bar.addWidget(self.btn_open_log)
        preset_bar.addWidget(self.btn_view_memory)
        preset_bar.addWidget(self.btn_open_shots)
        preset_bar.addStretch()
        t_layout.addLayout(preset_bar)
        layout.addWidget(title_box)

        # 1. Profile Selector Box
        prof_box = QFrame()
        prof_box.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px;")
        pb_layout = QVBoxLayout(prof_box)
        pb_layout.setSpacing(6)

        p_row = QHBoxLayout()
        p_row.addWidget(QLabel("<b>1. Select Firefox Profile:</b>"))
        self.btn_reload = QPushButton("🔄")
        self.btn_reload.setToolTip("Reload profiles list")
        self.btn_reload.setFixedWidth(36)
        self.btn_reload.clicked.connect(self.reload_profiles)
        p_row.addStretch()
        p_row.addWidget(self.btn_reload)
        pb_layout.addLayout(p_row)

        self.profile_combo = QComboBox()
        self.profile_combo.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 7px; border: 1px solid #475569;")
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        pb_layout.addWidget(self.profile_combo)

        # Session Status Badge
        self.lbl_session_badge = QLabel("Checking session status...")
        self.lbl_session_badge.setStyleSheet("font-size: 11px; color: #cbd5e1; padding: 2px 4px;")
        pb_layout.addWidget(self.lbl_session_badge)

        self.chk_unlock_profile = QCheckBox("Automatically inspect & unlock profile if locked (Unlock Profile)")
        self.chk_unlock_profile.setChecked(True)
        self.chk_unlock_profile.setStyleSheet("color: #e2e8f0; font-weight: bold; margin-top: 4px;")
        pb_layout.addWidget(self.chk_unlock_profile)

        self.chk_pro_mode = QCheckBox("Automatically verify & turn on Professional Mode")
        self.chk_pro_mode.setChecked(True)
        self.chk_pro_mode.setStyleSheet("color: #e2e8f0; font-weight: bold; margin-top: 2px;")
        pb_layout.addWidget(self.chk_pro_mode)

        self.chk_diagnostic_shots = QCheckBox("Save diagnostic screenshots on errors (data/agent_shots)")
        self.chk_diagnostic_shots.setChecked(True)
        self.chk_diagnostic_shots.setStyleSheet("color: #94a3b8; font-size: 11px; margin-top: 2px;")
        pb_layout.addWidget(self.chk_diagnostic_shots)

        layout.addWidget(prof_box)

        # 2. Ad Creative Section
        creative_box = QFrame()
        creative_box.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px;")
        c_layout = QVBoxLayout(creative_box)
        c_layout.setSpacing(8)

        lbl_creative = QLabel("<b>2. Ad Content & Creative Details:</b>")
        lbl_creative.setStyleSheet("color: #38bdf8; font-size: 13px;")
        c_layout.addWidget(lbl_creative)

        c_layout.addWidget(QLabel("Website Landing Page Link (Destination URL):"))
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("https://yourwebsite.com/landing-page")
        self.input_url.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 7px;")
        c_layout.addWidget(self.input_url)

        c_layout.addWidget(QLabel("Ad Headline:"))
        self.input_headline = QLineEdit()
        self.input_headline.setPlaceholderText("e.g., Get 50% Off Today Only!")
        self.input_headline.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 7px;")
        c_layout.addWidget(self.input_headline)

        c_layout.addWidget(QLabel("Ad Description (Primary Copy):"))
        self.input_desc = QTextEdit()
        self.input_desc.setPlaceholderText("Enter your complete ad copy here...")
        self.input_desc.setMaximumHeight(85)
        self.input_desc.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 7px;")
        c_layout.addWidget(self.input_desc)

        # CTA Button Selection
        c_layout.addWidget(QLabel("Action Button (CTA):"))
        self.cta_combo = QComboBox()
        self.cta_combo.addItems(["Learn More", "Shop Now", "Sign Up", "Contact Us", "Apply Now", "Book Now"])
        self.cta_combo.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 7px;")
        c_layout.addWidget(self.cta_combo)

        # Image Picker
        c_layout.addWidget(QLabel("Creative Image File (Optional):"))
        img_row = QHBoxLayout()
        self.input_img_path = QLineEdit()
        self.input_img_path.setPlaceholderText("Optional path to image file...")
        self.input_img_path.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 7px;")
        self.btn_browse = QPushButton("Browse Image...")
        self.btn_browse.setStyleSheet("background-color: #334155; color: #ffffff; padding: 7px 14px; font-weight: bold;")
        self.btn_browse.clicked.connect(self._browse_image)
        img_row.addWidget(self.input_img_path)
        img_row.addWidget(self.btn_browse)
        c_layout.addLayout(img_row)

        layout.addWidget(creative_box)

        # 3. Targeting & Budget Section
        target_box = QFrame()
        target_box.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px;")
        tb_layout = QVBoxLayout(target_box)
        tb_layout.setSpacing(8)

        lbl_target = QLabel("<b>3. Targeting, European Payee & Budget:</b>")
        lbl_target.setStyleSheet("color: #38bdf8; font-size: 13px;")
        tb_layout.addWidget(lbl_target)

        tb_layout.addWidget(QLabel("Target Countries (Comma-separated):"))
        self.input_countries = QLineEdit()
        self.input_countries.setText("United States, United Kingdom, Germany")
        self.input_countries.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 7px;")
        tb_layout.addWidget(self.input_countries)

        tb_layout.addWidget(QLabel("European Compliance Payee Name (Auto-randomized if blank):"))
        self.input_payee = QLineEdit()
        self.input_payee.setPlaceholderText("Leave blank for auto-generated compliant business name")
        self.input_payee.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 7px;")
        tb_layout.addWidget(self.input_payee)

        # Budget & Duration
        b_row = QHBoxLayout()
        b_row.addWidget(QLabel("Daily Budget ($):"))
        self.spin_budget = QDoubleSpinBox()
        self.spin_budget.setRange(1.0, 10000.0)
        self.spin_budget.setValue(5.0)
        self.spin_budget.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 5px;")
        b_row.addWidget(self.spin_budget)

        b_row.addWidget(QLabel("Duration (Days):"))
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(1, 90)
        self.spin_duration.setValue(7)
        self.spin_duration.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 5px;")
        b_row.addWidget(self.spin_duration)
        tb_layout.addLayout(b_row)

        layout.addWidget(target_box)

        # Action Control Panel (Launch, Pause, Resume, Abort)
        act_box = QFrame()
        act_box.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 10px;")
        act_layout = QHBoxLayout(act_box)
        act_layout.setSpacing(8)

        self.btn_launch_auto_ads = QPushButton("🚀 Launch Auto Ads")
        self.btn_launch_auto_ads.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_launch_auto_ads.clicked.connect(self._start_auto_ads)

        self.btn_pause = QPushButton("⏸️ Pause")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setStyleSheet("background-color: #d97706; color: #ffffff; padding: 10px 14px; font-weight: bold; border-radius: 6px;")
        self.btn_pause.clicked.connect(self._toggle_pause)

        self.btn_abort = QPushButton("⏹️ Abort")
        self.btn_abort.setEnabled(False)
        self.btn_abort.setStyleSheet("background-color: #dc2626; color: #ffffff; padding: 10px 14px; font-weight: bold; border-radius: 6px;")
        self.btn_abort.clicked.connect(self._abort_auto_ads)

        act_layout.addWidget(self.btn_launch_auto_ads, stretch=3)
        act_layout.addWidget(self.btn_pause, stretch=1)
        act_layout.addWidget(self.btn_abort, stretch=1)
        layout.addWidget(act_box)

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area, stretch=5)

        # =====================================================================
        # RIGHT COLUMN: Step-by-Step Checklist & Live Console
        # =====================================================================
        right_frame = QFrame()
        right_frame.setStyleSheet("background-color: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px;")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setSpacing(10)

        # Step-by-Step Execution Checklist Card
        step_card = QFrame()
        step_card.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px;")
        sc_layout = QVBoxLayout(step_card)
        sc_layout.setSpacing(4)

        lbl_step_hdr = QLabel("<b>📋 Execution Stages Checklist:</b>")
        lbl_step_hdr.setStyleSheet("color: #38bdf8; font-size: 12px;")
        sc_layout.addWidget(lbl_step_hdr)

        self.step_labels = []
        for i, text in enumerate(STEPS_DESCRIPTIONS, 1):
            lbl = QLabel(f"⚪ Stage {i}: {text}")
            lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            self.step_labels.append(lbl)
            sc_layout.addWidget(lbl)
        right_layout.addWidget(step_card)

        # Terminal Bar & Controls
        term_bar = QHBoxLayout()
        term_title = QLabel("📟 Live Execution Console")
        term_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")

        self.chk_autoscroll = QCheckBox("Auto-scroll")
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.setStyleSheet("color: #94a3b8; font-size: 11px;")

        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet("background-color: #334155; color: #f8fafc; padding: 3px 10px; font-size: 11px;")
        btn_clear.clicked.connect(lambda: self.console_output.clear())

        btn_log_folder = QPushButton("📂 Logs Folder")
        btn_log_folder.setStyleSheet("background-color: #334155; color: #f8fafc; padding: 3px 10px; font-size: 11px;")
        btn_log_folder.clicked.connect(self._open_logs_folder)

        term_bar.addWidget(term_title)
        term_bar.addStretch()
        term_bar.addWidget(self.chk_autoscroll)
        term_bar.addWidget(btn_clear)
        term_bar.addWidget(btn_log_folder)
        right_layout.addLayout(term_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                height: 18px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 3px;
            }
        """)
        right_layout.addWidget(self.progress_bar)

        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet("""
            QTextEdit {
                background-color: #020617;
                color: #e2e8f0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #1e293b;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        right_layout.addWidget(self.console_output)

        # Human-in-the-Loop Info Card
        info_box = QFrame()
        info_box.setStyleSheet("background-color: #1e1b4b; border: 1px solid #4338ca; border-radius: 6px; padding: 10px;")
        ib_layout = QVBoxLayout(info_box)
        lbl_info_title = QLabel("🛡️ Smart Safety & Human-in-the-Loop Active:")
        lbl_info_title.setStyleSheet("font-weight: bold; color: #a5b4fc; font-size: 11px;")
        lbl_info_body = QLabel(
            "• Zero in-flight user prompts: Sab inputs yahan pehle le liye gaye hain.\n"
            "• Agar Facebook phone verification, 2FA, ya payment challenge mange to window saamne aye gi aur automation pause ho gi.\n"
            "• Browser me challenge complete karein aur phir 'Resume' button dabayein."
        )
        lbl_info_body.setStyleSheet("color: #e0e7ff; font-size: 11px;")
        ib_layout.addWidget(lbl_info_title)
        ib_layout.addWidget(lbl_info_body)
        right_layout.addWidget(info_box)

        main_layout.addWidget(right_frame, stretch=5)

        self.reload_profiles()

    def reload_profiles(self):
        """Populate profile selector with registered profiles and session status."""
        self.profile_combo.clear()
        profiles = db.list_profiles()
        for p in profiles:
            status = system_automation.check_facebook_session_status(p.directory_name)
            is_running = process_manager.is_running(p.id)
            state_str = "🟢 Logged In" if status.get("logged_in") else "⚪ Logged Out"
            run_str = " [RUNNING]" if is_running else ""
            self.profile_combo.addItem(f"{p.name} - {state_str}{run_str}", p.id)

        self._on_profile_selected()

    def _on_profile_selected(self):
        profile_id = self.profile_combo.currentData()
        if not profile_id:
            self.lbl_session_badge.setText("No profile selected")
            return

        profile = db.get_profile(profile_id)
        if profile:
            status = system_automation.check_facebook_session_status(profile.directory_name)
            if status.get("logged_in"):
                c_user = status.get("c_user", "Unknown")
                self.lbl_session_badge.setText(f"🟢 Active Facebook Session Confirmed (User ID: {c_user})")
                self.lbl_session_badge.setStyleSheet("color: #4ade80; font-weight: bold;")
            else:
                self.lbl_session_badge.setText("⚠️ Not Logged In: Please log in to Facebook first via OS Automation tab.")
                self.lbl_session_badge.setStyleSheet("color: #f87171; font-weight: bold;")

    def _open_selected_profile(self):
        profile_id = self.profile_combo.currentData()
        if not profile_id:
            QMessageBox.warning(self, "Profile Required", "Please select a profile first.")
            return

        if process_manager.is_running(profile_id):
            process_manager.bring_to_front(profile_id)
            self.log_to_console(f"Brought running Firefox profile '{profile_id}' to front.")
        else:
            pid = profile_manager.launch_profile(profile_id, initial_url="https://www.facebook.com/")
            self.log_to_console(f"Launched Firefox profile '{profile_id}' (PID: {pid}).")
        self.reload_profiles()

    def _fill_quick_preset(self):
        """Fill high-converting default demo inputs for fast testing."""
        self.input_url.setText("https://example.com/exclusive-offer")
        self.input_headline.setText("Special Limited Offer - 50% Off Today!")
        self.input_desc.setText(
            "Discover premium quality solutions curated just for you. "
            "Claim your exclusive discount now with free express delivery worldwide!"
        )
        self.cta_combo.setCurrentText("Shop Now")
        self.input_countries.setText("United States, United Kingdom, Germany")
        self.spin_budget.setValue(5.0)
        self.spin_duration.setValue(7)
        self.log_to_console("⚡ Quick Demo Preset loaded successfully into form.")

    def _browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Creative Image", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if file_path:
            self.input_img_path.setText(file_path)

    def log_to_console(self, msg: str):
        self.console_output.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if self.chk_autoscroll.isChecked():
            self.console_output.verticalScrollBar().setValue(
                self.console_output.verticalScrollBar().maximum()
            )

    def _start_auto_ads(self):
        profile_id = self.profile_combo.currentData()
        url = self.input_url.text().strip()
        headline = self.input_headline.text().strip()
        desc = self.input_desc.toPlainText().strip()

        if not profile_id:
            QMessageBox.warning(self, "Profile Required", "Please select a Firefox profile.")
            return

        if not url or not headline or not desc:
            QMessageBox.warning(
                self,
                "Incomplete Inputs",
                "Please fill in Destination URL, Headline, and Description before launching.\n"
                "Tip: You can click '⚡ Quick Fill Demo Preset' to automatically fill demo data."
            )
            return

        countries = [c.strip() for c in self.input_countries.text().split(",") if c.strip()]
        if not countries:
            countries = ["United States"]

        config = AutoAdsConfig(
            profile_id=profile_id,
            target_url=url,
            ad_headline=headline,
            ad_description=desc,
            cta_button=self.cta_combo.currentText(),
            image_path=self.input_img_path.text().strip() or None,
            target_countries=countries,
            payee_name=self.input_payee.text().strip() or None,
            daily_budget=self.spin_budget.value(),
            duration_days=self.spin_duration.value(),
            enable_pro_mode=self.chk_pro_mode.isChecked(),
            unlock_profile_if_locked=self.chk_unlock_profile.isChecked(),
            diagnostic_screenshots=self.chk_diagnostic_shots.isChecked(),
        )

        # Reset UI stages
        for i, lbl in enumerate(self.step_labels, 1):
            lbl.setText(f"⚪ Stage {i}: {STEPS_DESCRIPTIONS[i - 1]}")
            lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")

        self.btn_launch_auto_ads.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("⏸️ Pause")
        self.btn_abort.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_to_console("🚀 Starting Auto Ads execution...")

        self.worker = AutoAdsWorker(config)
        self.worker.log_signal.connect(self.log_to_console)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _toggle_pause(self):
        if not self.worker or not self.worker.isRunning():
            return
        if auto_ads_engine.is_paused:
            auto_ads_engine.resume()
            self.btn_pause.setText("⏸️ Pause")
            self.btn_pause.setStyleSheet("background-color: #d97706; color: #ffffff; padding: 10px 14px; font-weight: bold; border-radius: 6px;")
            self.log_to_console("▶️ Resume signal delivered to automation.")
        else:
            auto_ads_engine.pause()
            self.btn_pause.setText("▶️ Resume")
            self.btn_pause.setStyleSheet("background-color: #16a34a; color: #ffffff; padding: 10px 14px; font-weight: bold; border-radius: 6px;")
            self.log_to_console("⏸️ Pause signal delivered to automation.")

    def _abort_auto_ads(self):
        if self.worker and self.worker.isRunning():
            auto_ads_engine.stop()
            self.log_to_console("⏹️ Abort signal delivered. Stopping execution...")
            self.btn_pause.setEnabled(False)
            self.btn_abort.setEnabled(False)

    def _on_progress(self, current: int, total: int):
        pct = int((current / total) * 100)
        self.progress_bar.setValue(pct)

        # Update checklist labels
        for i, lbl in enumerate(self.step_labels, 1):
            if i < current:
                lbl.setText(f"✅ Stage {i}: {STEPS_DESCRIPTIONS[i - 1]}")
                lbl.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")
            elif i == current:
                lbl.setText(f"⏳ Stage {i}: {STEPS_DESCRIPTIONS[i - 1]} (In Progress)")
                lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
            else:
                lbl.setText(f"⚪ Stage {i}: {STEPS_DESCRIPTIONS[i - 1]}")
                lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")

    def _on_finished(self, success: bool, message: str):
        self.btn_launch_auto_ads.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸️ Pause")
        self.btn_abort.setEnabled(False)
        self.progress_bar.setValue(100 if success else 0)

        if success:
            for i, lbl in enumerate(self.step_labels, 1):
                lbl.setText(f"✅ Stage {i}: {STEPS_DESCRIPTIONS[i - 1]}")
                lbl.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")
            self.log_to_console(f"🎉 {message}")
            QMessageBox.information(self, "Auto Ads Completed", message)
        else:
            self.log_to_console(f"❌ {message}")
            QMessageBox.critical(self, "Auto Ads Error", message)

    def _open_profile_log(self):
        """Open the dedicated log file for the selected profile in default text editor."""
        profile_id = self.profile_combo.currentData()
        if not profile_id:
            QMessageBox.warning(self, "Profile Required", "Please select a profile to view its log.")
            return

        import os
        log_path = profile_logger.get_profile_log_path(profile_id)
        if not log_path.exists():
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(f"--- Log started for profile ID: {profile_id} ---\n", encoding="utf-8")

        os.startfile(str(log_path))

    def _open_logs_folder(self):
        """Open the base profiles logs folder in Windows File Explorer."""
        import os
        logs_dir = profile_logger.get_logs_dir()
        os.startfile(str(logs_dir))

    def _open_screenshots_folder(self):
        """Open the diagnostic screenshots directory in Windows File Explorer."""
        import os
        shot_dir = agent_recovery.shot_dir
        shot_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(shot_dir))

    def _show_memory_dialog(self):
        """Display learned heuristic scores and performance stats."""
        stats = agent_memory.get_stats()
        heuristics_count = stats.get("total_heuristics", 0)
        successes = stats.get("total_successes", 0)
        failures = stats.get("total_failures", 0)
        rate = stats.get("overall_success_rate", 0.0) * 100

        top_lines = []
        for item in stats.get("top_performers", [])[:10]:
            top_lines.append(f"• {item['key']}: {item['score']:.2f} score ({item['ok']} ok, {item['fail']} fail)")

        top_str = "\n".join(top_lines) if top_lines else "No historical heuristics recorded yet."

        msg = (
            f"<b>🧠 Self-Learning Ad Automation Memory Stats</b><br><br>"
            f"<b>Total Learned Strategies:</b> {heuristics_count}<br>"
            f"<b>Historical Successes:</b> {successes}<br>"
            f"<b>Historical Failures:</b> {failures}<br>"
            f"<b>Overall Success Rate:</b> {rate:.1f}%<br><br>"
            f"<b>Top Performing Strategies & Fixes:</b><br>"
            f"<pre>{top_str}</pre><br>"
            f"<i>Memory File:</i> {stats.get('memory_file')}"
        )
        box = QMessageBox(self)
        box.setWindowTitle("Self-Learning Agent Memory")
        box.setTextFormat(Qt.RichText)
        box.setText(msg)
        btn_reset = box.addButton("Reset Memory", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Ok)
        box.exec()

        if box.clickedButton() == btn_reset:
            agent_memory.clear()
            self.log_to_console("🧠 Agent memory store has been reset to defaults.")
