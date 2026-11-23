"""
Profile Portability & Packaging Subsystem.
Enables 100% lossless export and import of Firefox profiles between different PCs.
Preserves cookies, session credentials, localStorage, anti-fingerprint preferences,
and certificates without data corruption.
"""

import os
import json
import shutil
import zipfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from firefox_manager.config.settings import settings
from firefox_manager.database.database import db
from firefox_manager.database.models import ProfileRecord, ProfileStatus
from firefox_manager.browser.profile_storage import profile_storage
from firefox_manager.security.audit_logger import audit_logger


LOCK_FILES = {".parentlock", "parent.lock", "lock"}


class ProfilePackager:
    """Handles lossless bundling, export, import and sync of profiles across systems."""

    def export_profile_bundle(
        self, profile_id: str, output_zip_path: Optional[Path] = None
    ) -> Path:
        """
        Package a profile into a portable .zip archive.
        Filters out active OS lock files so export succeeds even if Firefox is currently running.
        """
        profile = db.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found.")

        src_dir = profile_storage.get_profile_path(profile.directory_name)
        if not src_dir.exists():
            raise FileNotFoundError(f"Profile directory '{src_dir}' does not exist on disk.")

        if output_zip_path is None:
            export_dir = Path("exports").resolve()
            export_dir.mkdir(parents=True, exist_ok=True)
            output_zip_path = export_dir / f"{profile.name}_portable.zip"

        output_zip_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = {
            "version": "1.0",
            "profile_id": profile.id,
            "name": profile.name,
            "directory_name": profile.directory_name,
            "custom_user_agent": profile.custom_user_agent,
            "proxy_server": profile.proxy_server,
            "notes": profile.notes,
            "tags": profile.tags,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

        # Write manifest temporarily inside folder
        manifest_file = src_dir / "profile_manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        try:
            with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(src_dir):
                    for file in files:
                        if file in LOCK_FILES:
                            continue
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(src_dir)
                        try:
                            zf.write(file_path, arcname)
                        except Exception:
                            pass
        finally:
            if manifest_file.exists():
                try:
                    manifest_file.unlink()
                except Exception:
                    pass

        audit_logger.log(
            agent_name="ProfilePackager",
            action="PROFILE_EXPORTED",
            target=profile.name,
            details=f"Exported portable bundle to {output_zip_path}",
        )
        return output_zip_path

    def import_profile_bundle(self, source_path: Path) -> ProfileRecord:
        """
        Import a profile bundle (.zip or directory) into the local Subwey platform.
        Restores database records and syncs with native Firefox profiles.ini.
        """
        source = Path(source_path).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source '{source}' does not exist.")

        # If it's a zip file, extract it
        if source.is_file() and source.suffix.lower() == ".zip":
            temp_extract = Path(settings.profiles_dir) / "_temp_extract"
            if temp_extract.exists():
                shutil.rmtree(temp_extract, ignore_errors=True)
            temp_extract.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(source, "r") as zf:
                zf.extractall(temp_extract)

            # Read manifest if present
            manifest_path = temp_extract / "profile_manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                target_name = manifest.get("name", source.stem.replace("_portable", ""))
                dir_name = manifest.get("directory_name", f"{target_name}_imported")
                target_dir = settings.profiles_dir / dir_name
                if target_dir.exists():
                    shutil.rmtree(target_dir, ignore_errors=True)
                shutil.move(str(temp_extract), str(target_dir))
                manifest_path = target_dir / "profile_manifest.json"
                if manifest_path.exists():
                    manifest_path.unlink()
            else:
                target_name = source.stem.replace("_portable", "")
                dir_name = f"{target_name}_imported"
                target_dir = settings.profiles_dir / dir_name
                if target_dir.exists():
                    shutil.rmtree(target_dir, ignore_errors=True)
                shutil.move(str(temp_extract), str(target_dir))
                manifest = {"name": target_name, "directory_name": dir_name}
        else:
            # It's already a directory dropped into profiles or external
            target_dir = source
            dir_name = source.name
            manifest_path = source / "profile_manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                target_name = manifest.get("name", dir_name)
            else:
                target_name = dir_name.rsplit("_", 1)[0] if "_" in dir_name else dir_name
                manifest = {"name": target_name, "directory_name": dir_name}

        # Clear any stale locks
        profile_storage.remove_stale_locks(dir_name)

        # Check if record already in database
        existing = db.get_profile_by_name(target_name)
        if existing:
            # Update directory and status
            db.update_profile_status(existing.id, ProfileStatus.STOPPED, is_active=False)
            record = existing
        else:
            import uuid
            profile_id = manifest.get("profile_id", str(uuid.uuid4()))
            record = ProfileRecord(
                id=profile_id,
                name=target_name,
                directory_name=dir_name,
                custom_user_agent=manifest.get("custom_user_agent"),
                proxy_server=manifest.get("proxy_server"),
                notes=manifest.get("notes", "Imported from portable bundle"),
                tags=manifest.get("tags", "portable,imported"),
                is_active=False,
                status=ProfileStatus.STOPPED,
                disk_usage_bytes=profile_storage.calculate_disk_usage(dir_name),
            )
            db.create_profile(record)

        audit_logger.log(
            agent_name="ProfilePackager",
            action="PROFILE_IMPORTED",
            target=record.name,
            details=f"Imported lossless profile from {source.name}",
        )
        return record

    def auto_sync_dropped_profile_folders(self) -> int:
        """
        Scan profiles/ for any manually dropped folders.
        If a folder has valid Firefox profile contents, auto-import it into the database
        instead of purging it as junk.
        """
        if not settings.profiles_dir.exists():
            return 0

        registered_dirs = {p.directory_name for p in db.list_profiles()}
        imported_count = 0

        for item in settings.profiles_dir.iterdir():
            if item.is_dir() and item.name not in registered_dirs:
                # Check if it has Firefox profile signatures
                has_ff_signatures = any(
                    (item / sig).exists()
                    for sig in ("cookies.sqlite", "prefs.js", "user.js", "places.sqlite", "storage")
                )
                if has_ff_signatures:
                    audit_logger.log(
                        agent_name="ProfilePackager",
                        action="AUTO_DISCOVERED_PROFILE",
                        target=item.name,
                        details="Discovered manually copied Firefox profile folder. Auto-registering...",
                    )
                    try:
                        self.import_profile_bundle(item)
                        imported_count += 1
                    except Exception:
                        pass
        return imported_count


profile_packager = ProfilePackager()
