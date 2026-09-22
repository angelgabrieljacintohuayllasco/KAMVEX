"""
Build the KAMVEX Windows installer.

Steps:
  1. Build the Python sidecar with PyInstaller (onefile) -> sidecar/dist/kamvex-sidecar.exe
  2. Copy it to src-tauri/binaries/kamvex-sidecar-<target-triple>.exe (Tauri externalBin)
  3. Build the Tauri app (npm run tauri build) -> NSIS installer + MSI

Usage:
    python scripts/build-installer.py              # everything
    python scripts/build-installer.py --sidecar-only
    python scripts/build-installer.py --skip-sidecar   # reuse an existing sidecar exe

Prerequisites:
    pip install -r sidecar/requirements.txt -r sidecar/requirements-dev.txt
    npm install
    Rust (MSVC toolchain) + Visual Studio Build Tools + WebView2 for `tauri build`
    TAURI_SIGNING_PRIVATE_KEY (+ _PASSWORD) because bundle.createUpdaterArtifacts is on
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIDECAR = ROOT / "sidecar"
BINARIES = ROOT / "src-tauri" / "binaries"
TAURI_TARGET = "x86_64-pc-windows-msvc"
SIDECAR_EXE = SIDECAR / "dist" / "kamvex-sidecar.exe"


def step(msg: str) -> None:
    print(f"\n{'=' * 60}\n  {msg}\n{'=' * 60}")


def run(cmd: str, cwd: Path | None = None) -> None:
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=str(cwd) if cwd else None)
    if result.returncode != 0:
        print(f"  ERROR: command failed with code {result.returncode}")
        sys.exit(1)


def which_or_die(tool: str, hint: str) -> None:
    if shutil.which(tool) is None:
        print(f"  ERROR: '{tool}' not found in PATH. {hint}")
        sys.exit(1)


def app_version() -> str:
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    return str(conf.get("version", "0.0.0"))


def build_sidecar() -> None:
    step("1/3: Building Python sidecar with PyInstaller (onefile)")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("  ERROR: PyInstaller not installed. Run: pip install -r sidecar/requirements-dev.txt")
        sys.exit(1)
    run(f'"{sys.executable}" -m PyInstaller kamvex-sidecar.spec --noconfirm --clean', cwd=SIDECAR)
    if not SIDECAR_EXE.exists():
        print(f"  ERROR: {SIDECAR_EXE} not found. PyInstaller build failed?")
        sys.exit(1)
    print(f"  Built {SIDECAR_EXE} ({SIDECAR_EXE.stat().st_size / 1e6:.1f} MB)")


def copy_sidecar() -> None:
    step("2/3: Copying sidecar to src-tauri/binaries/")
    if not SIDECAR_EXE.exists():
        print(f"  ERROR: {SIDECAR_EXE} missing (run without --skip-sidecar)")
        sys.exit(1)
    BINARIES.mkdir(parents=True, exist_ok=True)
    dest = BINARIES / f"kamvex-sidecar-{TAURI_TARGET}.exe"
    shutil.copy2(SIDECAR_EXE, dest)
    print(f"  Copied to {dest}")


def build_tauri() -> None:
    step("3/3: Building Tauri app (npm run tauri build)")
    which_or_die("npm", "Install Node.js 18+.")
    which_or_die("cargo", "Install Rust (rustup) with the MSVC toolchain.")
    if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        print("  WARNING: TAURI_SIGNING_PRIVATE_KEY is not set; the updater artifacts step will fail.")
        print("           Generate a key with `npm run tauri signer generate` or disable")
        print("           bundle.createUpdaterArtifacts in src-tauri/tauri.conf.json.")
    run("npm run tauri build", cwd=ROOT)
    ver = app_version()
    bundle = ROOT / "src-tauri" / "target" / "release" / "bundle"
    print("\n  Installers:")
    print(f"   - NSIS: {bundle / 'nsis' / f'KAMVEX_{ver}_x64-setup.exe'}")
    print(f"   - MSI:  {bundle / 'msi' / f'KAMVEX_{ver}_x64_en-US.msi'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sidecar-only", action="store_true", help="build + copy the sidecar, skip Tauri")
    ap.add_argument("--skip-sidecar", action="store_true", help="reuse sidecar/dist/kamvex-sidecar.exe")
    args = ap.parse_args()

    if not args.skip_sidecar:
        build_sidecar()
    copy_sidecar()
    if not args.sidecar_only:
        build_tauri()
    step("Done")


if __name__ == "__main__":
    main()
