"""
Build script for the Kamvex Windows installer.

Steps:
1. Build the Python sidecar with PyInstaller → standalone exe
2. Copy to src-tauri/binaries/ with the Tauri-expected name
3. Build the Tauri app (npm run tauri build) → NSIS installer + MSI

Usage:
    cd KAMVEX
    python scripts/build-installer.py

Prerequisites:
    pip install pyinstaller fastapi uvicorn numpy
    npm install
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIDECAR = ROOT / "sidecar"
BINARIES = ROOT / "src-tauri" / "binaries"
TAURI_TARGET = "x86_64-pc-windows-msvc"


def step(msg):
    print(f"\n{'=' * 60}\n  {msg}\n{'=' * 60}")


def run(cmd, cwd=None):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if result.returncode != 0:
        print(f"  ERROR: command failed with code {result.returncode}")
        sys.exit(1)


def main():
    step("1/4: Building Python sidecar with PyInstaller")
    run("pyinstaller kamvex-sidecar.spec --noconfirm", cwd=str(SIDECAR))

    step("2/4: Copying sidecar to Tauri binaries/")
    BINARIES.mkdir(parents=True, exist_ok=True)
    src = SIDECAR / "dist" / "kamvex-sidecar" / "kamvex-sidecar.exe"
    if not src.exists():
        print(f"  ERROR: {src} not found. PyInstaller build failed?")
        sys.exit(1)

    # Tauri expects: <name>-<target-triple>.exe
    dest = BINARIES / f"kamvex-sidecar-{TAURI_TARGET}.exe"
    shutil.copy2(src, dest)
    print(f"  Copied to {dest}")

    # PyInstaller produces a folder with DLLs — copy the whole folder
    dist_dir = SIDECAR / "dist" / "kamvex-sidecar"
    dest_dir = BINARIES / f"kamvex-sidecar-{TAURI_TARGET}"
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(dist_dir, dest_dir)
    print(f"  Copied folder to {dest_dir}")

    step("3/4: Building Tauri app (npm run tauri build)")
    run("npm run tauri build", cwd=str(ROOT))

    step("4/4: Done!")
    print("  Installer should be in src-tauri/target/release/bundle/")
    print("  - NSIS: nsis/KAMVEX_0.1.0_x64-setup.exe")
    print("  - MSI:  msi/KAMVEX_0.1.0_x64_en-US.msi")


if __name__ == "__main__":
    main()
