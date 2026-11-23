"""
Process Manager and Resource Monitor.
Tracks active Firefox processes, CPU/Memory metrics, crash detection,
and enforces concurrent execution limits.
"""

import sys
import time
import subprocess
import threading
from typing import Dict, Optional, Tuple, Callable, List
from pathlib import Path
import psutil

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import ProcessMetricRecord, ProfileStatus
from firefox_manager.security.audit_logger import audit_logger
from firefox_manager.browser.firefox_launcher import FirefoxLauncher


class ActiveProcessInfo:
    """Descriptor for a live managed Firefox process."""
    def __init__(self, profile_id: str, directory_name: str, process: subprocess.Popen):
        self.profile_id = profile_id
        self.directory_name = directory_name
        self.process = process
        self.pid = process.pid
        self.start_time = time.time()
        self._psutil_proc: Optional[psutil.Process] = None
        try:
            self._psutil_proc = psutil.Process(self.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def is_alive(self) -> bool:
        """Check if process is still executing."""
        if self.process.poll() is not None:
            return False
        if self._psutil_proc:
            return self._psutil_proc.is_running() and self._psutil_proc.status() != psutil.STATUS_ZOMBIE
        return True

    def get_metrics(self) -> Tuple[float, float]:
        """Return (cpu_percent, memory_mb)."""
        if not self._psutil_proc or not self.is_alive():
            return 0.0, 0.0
        try:
            # Non-blocking cpu_percent call
            cpu = self._psutil_proc.cpu_percent(interval=None)
            mem = self._psutil_proc.memory_info().rss / (1024 * 1024)
            return round(cpu, 1), round(mem, 1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0, 0.0


class ProcessManager:
    """Coordinates lifecycle of all active browser processes."""

    def __init__(self, launcher: Optional[FirefoxLauncher] = None):
        self.launcher = launcher or FirefoxLauncher()
        self._active_processes: Dict[str, ActiveProcessInfo] = {}  # profile_id -> info
        self._lock = threading.RLock()
        self._crash_callbacks: List[Callable[[str, int], None]] = []

    def register_crash_callback(self, cb: Callable[[str, int], None]) -> None:
        """Register hook invoked when a browser process unexpectedly terminates."""
        if cb not in self._crash_callbacks:
            self._crash_callbacks.append(cb)

    def get_active_count(self) -> int:
        """Return total running Firefox instances."""
        with self._lock:
            self._prune_dead()
            return len(self._active_processes)

    def is_running(self, profile_id: str) -> bool:
        """Check if profile has an active process."""
        with self._lock:
            info = self._active_processes.get(profile_id)
            if info and info.is_alive():
                return True
            if info:
                del self._active_processes[profile_id]
            return False

    def get_pid(self, profile_id: str) -> Optional[int]:
        """Return PID of profile if active."""
        with self._lock:
            info = self._active_processes.get(profile_id)
            if info and info.is_alive():
                return info.pid
            return None

    def launch_profile_process(
        self,
        profile_id: str,
        directory_name: str,
        profile_path: Path,
        initial_url: Optional[str] = None,
    ) -> int:
        """
        Launch Firefox for profile_id and register in process tracker.
        Enforces maximum concurrent profile limits.
        """
        with self._lock:
            self._prune_dead()

            if self.is_running(profile_id):
                raise RuntimeError(f"Profile '{profile_id}' is already running with PID {self.get_pid(profile_id)}")

            if len(self._active_processes) >= settings.max_concurrent_profiles:
                raise RuntimeError(
                    f"Maximum concurrent profile limit reached ({settings.max_concurrent_profiles}). "
                    f"Close an active profile before launching another."
                )

            process = self.launcher.launch(
                profile_path=profile_path,
                initial_url=initial_url,
            )

            info = ActiveProcessInfo(profile_id, directory_name, process)
            self._active_processes[profile_id] = info

            audit_logger.log(
                agent_name="ProcessManager",
                action="PROCESS_LAUNCHED",
                target=profile_id,
                details=f"PID {process.pid} on profile '{directory_name}'",
            )
            return process.pid

    def stop_profile_process(self, profile_id: str, timeout: Optional[float] = None) -> bool:
        """
        Gracefully terminate Firefox process and all descendant child processes.
        Uses process tree termination to ensure no child processes linger and lock files.
        """
        with self._lock:
            info = self._active_processes.get(profile_id)
            if not info:
                return True  # Already stopped

            pid = info.pid
            effective_timeout = timeout or settings.process_timeout_seconds

            # 1. Terminate entire process tree via psutil
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for c in children:
                    try:
                        c.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                parent.terminate()
                _, alive = psutil.wait_procs(children + [parent], timeout=min(effective_timeout, 4.0))
                for p in alive:
                    try:
                        p.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            # 2. Windows OS fallback: taskkill /F /PID <pid> /T
            if sys.platform == "win32":
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid), "/T"],
                        capture_output=True,
                        timeout=5.0,
                    )
                except Exception:
                    pass

            if profile_id in self._active_processes:
                del self._active_processes[profile_id]

            audit_logger.log(
                agent_name="ProcessManager",
                action="PROCESS_STOPPED",
                target=profile_id,
                details=f"PID {pid} and all child processes stopped successfully.",
            )
            return True

    def get_metrics_for_profile(self, profile_id: str) -> Tuple[float, float]:
        """Return (cpu_percent, memory_mb) for given profile."""
        with self._lock:
            info = self._active_processes.get(profile_id)
            if info:
                return info.get_metrics()
            return 0.0, 0.0

    def get_all_active_metrics(self) -> Dict[str, Tuple[float, float]]:
        """Return mapping of profile_id -> (cpu_percent, memory_mb)."""
        metrics = {}
        with self._lock:
            for pid_id, info in self._active_processes.items():
                if info.is_alive():
                    metrics[pid_id] = info.get_metrics()
        return metrics

    def bring_to_front(self, profile_id: str) -> bool:
        """Bring window of profile to foreground."""
        with self._lock:
            pid = self.get_pid(profile_id)
            if pid:
                return self.launcher.bring_window_to_front(pid)
            return False

    def _prune_dead(self) -> None:
        """Remove dead processes and trigger crash hooks if unexpected termination detected."""
        dead = []
        for pid_id, info in self._active_processes.items():
            if not info.is_alive():
                dead.append((pid_id, info))

        for pid_id, info in dead:
            del self._active_processes[pid_id]
            exit_code = info.process.poll() or 0
            audit_logger.log(
                agent_name="ProcessManager",
                action="PROCESS_EXIT_DETECTED",
                target=pid_id,
                details=f"Process {info.pid} exited with code {exit_code}",
            )
            # Notify crash callbacks
            for cb in self._crash_callbacks:
                try:
                    cb(pid_id, exit_code)
                except Exception:
                    pass

    def shutdown_all(self) -> None:
        """Cleanly shutdown all running browser instances on application exit."""
        with self._lock:
            active_ids = list(self._active_processes.keys())
            for pid_id in active_ids:
                try:
                    self.stop_profile_process(pid_id, timeout=3.0)
                except Exception:
                    pass

        # Sweep stray Firefox processes ONLY if their command line points
        # inside the managed profiles_dir. The old code also killed any
        # process whose cmdline merely contained "-profile", which could
        # kill the user's unrelated Firefox profiles.
        try:
            profiles_str = str(settings.profiles_dir.resolve()).lower()
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    if proc.info.get("name") and "firefox" in proc.info["name"].lower():
                        cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                        if profiles_str in cmdline:
                            proc.kill()
                except Exception:
                    pass
        except Exception:
            pass


# Global process manager
process_manager = ProcessManager()

