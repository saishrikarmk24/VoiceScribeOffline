"""VoiceScribe AI - Distribution Packager.

Creates a clean, lightweight zip file for distribution to colleagues and friends.
Excludes virtual environments, node_modules, local database files, logs, and caches.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path


def create_distribution_zip(
    output_name: str = "VoiceScribe_AI_Offline_Setup.zip",
) -> Path:
    root_dir = Path(__file__).resolve().parent
    output_path = root_dir / output_name

    # Directories to ignore
    exclude_dirs = {
        ".git",
        ".github",
        ".venv",
        ".venvs",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".claude",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "coverage",
    }

    # Extensions to ignore
    exclude_extensions = {
        ".pyc",
        ".pyo",
        ".pyd",
        ".db",
        ".db-shm",
        ".db-wal",
        ".log",
        ".zip",
    }

    print("==============================================================================")
    print("                 VOICESCRIBE AI - CLEAN PACKAGE BUILDER")
    print("==============================================================================")
    print(f"Source:      {root_dir}")
    print(f"Destination: {output_path}")
    print("------------------------------------------------------------------------------")

    # If the zip already exists, delete it first
    if output_path.exists():
        try:
            output_path.unlink()
        except Exception as exc:
            print(f"[WARNING] Could not delete old zip file: {exc}")

    # Ensure backend/storage/audio directory exists with a placeholder if empty
    audio_dir = root_dir / "backend" / "storage" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = audio_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

    files_to_pack: list[tuple[Path, str]] = []
    total_uncompressed_bytes = 0

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # In-place filter out excluded directories
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()

            # Skip target zip itself
            if fpath.resolve() == output_path.resolve():
                continue

            # Skip excluded extensions
            if ext in exclude_extensions:
                continue

            # Skip temporary recorded audio files in storage/audio (keep only .gitkeep)
            if "storage" in fpath.parts and "audio" in fpath.parts and fname != ".gitkeep":
                continue

            # Relative path within zip archive
            arcname = os.path.relpath(fpath, root_dir)
            files_to_pack.append((fpath, arcname))
            total_uncompressed_bytes += fpath.stat().st_size

    print(f"Files selected: {len(files_to_pack)}")
    print(f"Uncompressed size: {total_uncompressed_bytes / (1024 * 1024):.2f} MB")
    print("Compressing archive (optimal deflate)...")

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for fpath, arcname in files_to_pack:
            zf.write(fpath, arcname)

    compressed_size_mb = output_path.stat().st_size / (1024 * 1024)
    print("------------------------------------------------------------------------------")
    print(f"[SUCCESS] Package created: {output_path.name}")
    print(f"Compressed size: {compressed_size_mb:.2f} MB")
    print("==============================================================================")
    print("Ready to share with friends/clinicians!")
    print("When they extract the zip, they only need to run:")
    print("    --> ONE_CLICK_INSTALL_AND_START.bat")
    print("==============================================================================")
    return output_path


if __name__ == "__main__":
    try:
        create_distribution_zip()
    except Exception as e:
        print(f"[ERROR] Failed to create package: {e}")
        sys.exit(1)
