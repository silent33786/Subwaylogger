"""
Self-Learning Memory System for Ad Automation.
Maintains persistent success/failure records for selectors, coordinate strategies,
and recovery actions across executions.
Uses Laplace smoothing for Bayesian success probability scoring.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from firefox_manager.config.settings import settings

logger = logging.getLogger("AutoAdsMemory")


class AdAgentMemory:
    """
    Self-learning memory store that learns which selectors, coordinate anchors,
    and recovery routines work best over time.
    """

    def __init__(self, memory_file: Optional[Path] = None):
        if memory_file:
            self.memory_file = Path(memory_file)
        else:
            data_dir = getattr(settings, "data_dir", Path("data"))
            self.memory_file = Path(data_dir) / "agent_memory.json"

        self._lock = threading.RLock()
        # Best-effort cross-process file lock: a sibling .lock directory
        # created atomically with os.mkdir (fails if it already exists).
        # The old code had only a per-instance threading lock, so two
        # processes / engines writing at once silently lost each other's
        # updates (last writer won). Directory locks are stale-safe via
        # a timestamp file and a 10s timeout.
        self._file_lock_path = self.memory_file.with_suffix(".lock")
        self.data: Dict[str, Dict[str, int]] = {}
        self.load()

    # -- cross-process file lock (best effort, never blocks forever) --
    def _acquire_file_lock(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            try:
                self._file_lock_path.mkdir(parents=True, exist_ok=False)
                (self._file_lock_path / "pid").write_text(str(os.getpid()), encoding="utf-8")
                return True
            except FileExistsError:
                # Stale lock? A lock older than the timeout is treated as stale.
                try:
                    mtime = self._file_lock_path.stat().st_mtime
                    if time.time() - mtime > timeout:
                        import shutil
                        shutil.rmtree(self._file_lock_path, ignore_errors=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    logger.warning("Could not acquire memory file lock; proceeding without it.")
                    return False
                time.sleep(0.05)
            except OSError:
                return False

    def _release_file_lock(self) -> None:
        try:
            import shutil
            shutil.rmtree(self._file_lock_path, ignore_errors=True)
        except Exception:
            pass

    def load(self) -> None:
        """Load stored memory data from disk."""
        with self._lock:
            try:
                if self.memory_file.exists():
                    raw = self.memory_file.read_text(encoding="utf-8")
                    self.data = json.loads(raw)
                else:
                    self.data = {}
            except Exception as e:
                logger.warning(f"Could not load memory file {self.memory_file}: {e}")
                self.data = {}

    def save(self, merge: bool = True) -> None:
        """Persist memory data to disk atomically, under the file lock."""
        with self._lock:
            locked = self._acquire_file_lock()
            try:
                # Re-read under the lock so a concurrent writer's data
                # is not silently overwritten by this process's snapshot.
                # merge=False is used by clear(): merging would resurrect
                # the just-cleared data from disk.
                if merge and self.memory_file.exists():
                    try:
                        on_disk = json.loads(self.memory_file.read_text(encoding="utf-8"))
                        if isinstance(on_disk, dict):
                            merged = dict(on_disk)
                            merged.update(self.data)
                            self.data = merged
                    except Exception:
                        pass
                self.memory_file.parent.mkdir(parents=True, exist_ok=True)
                temp_file = self.memory_file.with_suffix(".tmp")
                temp_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
                temp_file.replace(self.memory_file)
            except Exception as e:
                logger.error(f"Failed to save agent memory: {e}")
            finally:
                if locked:
                    self._release_file_lock()

    def _get_record(self, key: str) -> Dict[str, int]:
        return self.data.setdefault(key, {"ok": 0, "fail": 0})

    def _peek_record(self, key: str) -> Dict[str, int]:
        # Read-only peek: never creates an entry. score() used to call
        # setdefault, so merely ranking candidates polluted the file
        # with a key for every candidate ever considered.
        rec = self.data.get(key)
        if isinstance(rec, dict):
            return {"ok": int(rec.get("ok", 0)), "fail": int(rec.get("fail", 0))}
        return {"ok": 0, "fail": 0}

    def record(self, key: str, ok: bool) -> None:
        """
        Record a trial outcome for a strategy, selector, or fix.
        Increment 'ok' on success or 'fail' on failure and persist immediately.
        """
        with self._lock:
            rec = self._get_record(key)
            if ok:
                rec["ok"] += 1
            else:
                rec["fail"] += 1
            self.save()

    def score(self, key: str) -> float:
        """
        Bayesian smoothed probability score using Laplace smoothing:
        (ok + 1) / (ok + fail + 2)
        Prior is uniform 0.5 when no historical data exists.
        Does NOT mutate data (read-only).
        """
        with self._lock:
            rec = self._peek_record(key)
            return (rec["ok"] + 1.0) / (rec["ok"] + rec["fail"] + 2.0)

    def rank(self, scope: str, options: List[str]) -> List[str]:
        """
        Rank candidate strategies/options descending by their smoothed success score.
        Scope provides context (e.g., 'click_publish', 'fix|stage_goal', etc.).
        """
        with self._lock:
            return sorted(
                options,
                key=lambda opt: self.score(f"{scope}|{opt}"),
                reverse=True,
            )

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostic statistics of learned memory (read-only)."""
        with self._lock:
            # Snapshot without creating entries: score() is now
            # non-mutating, but build the list from a copy anyway.
            snapshot = {
                k: {"ok": int(v.get("ok", 0)), "fail": int(v.get("fail", 0))}
                for k, v in self.data.items()
                if isinstance(v, dict)
            }
            total_keys = len(snapshot)
            total_ok = sum(v["ok"] for v in snapshot.values())
            total_fail = sum(v["fail"] for v in snapshot.values())
            top_performers = sorted(
                [
                    {"key": k, "ok": v["ok"], "fail": v["fail"],
                     "score": (v["ok"] + 1.0) / (v["ok"] + v["fail"] + 2.0)}
                    for k, v in snapshot.items()
                    if v["ok"] + v["fail"] > 0
                ],
                key=lambda x: x["score"],
                reverse=True,
            )[:15]

            return {
                "total_heuristics": total_keys,
                "total_successes": total_ok,
                "total_failures": total_fail,
                "overall_success_rate": round(total_ok / max(1, total_ok + total_fail), 3),
                "top_performers": top_performers,
                "memory_file": str(self.memory_file),
            }

    def clear(self) -> None:
        """Reset memory store."""
        with self._lock:
            self.data = {}
            self.save(merge=False)


# Global singleton instance
agent_memory = AdAgentMemory()
