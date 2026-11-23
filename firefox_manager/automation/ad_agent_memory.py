"""
Self-Learning Memory System for Ad Automation.
Maintains persistent success/failure records for selectors, coordinate strategies,
and recovery actions across executions.
Uses Laplace smoothing for Bayesian success probability scoring.
"""

import json
import logging
import threading
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
        self.data: Dict[str, Dict[str, int]] = {}
        self.load()

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

    def save(self) -> None:
        """Persist memory data to disk atomically."""
        with self._lock:
            try:
                self.memory_file.parent.mkdir(parents=True, exist_ok=True)
                temp_file = self.memory_file.with_suffix(".tmp")
                temp_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
                temp_file.replace(self.memory_file)
            except Exception as e:
                logger.error(f"Failed to save agent memory: {e}")

    def _get_record(self, key: str) -> Dict[str, int]:
        return self.data.setdefault(key, {"ok": 0, "fail": 0})

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
        """
        with self._lock:
            rec = self._get_record(key)
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
        """Return diagnostic statistics of learned memory."""
        with self._lock:
            total_keys = len(self.data)
            total_ok = sum(v.get("ok", 0) for v in self.data.values())
            total_fail = sum(v.get("fail", 0) for v in self.data.values())
            top_performers = sorted(
                [
                    {"key": k, "ok": v.get("ok", 0), "fail": v.get("fail", 0), "score": self.score(k)}
                    for k, v in self.data.items()
                    if v.get("ok", 0) + v.get("fail", 0) > 0
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
            self.save()


# Global singleton instance
agent_memory = AdAgentMemory()
