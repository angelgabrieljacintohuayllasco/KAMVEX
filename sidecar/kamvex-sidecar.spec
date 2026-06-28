"""
PyInstaller spec for building the Kamvex Python sidecar into a standalone exe.

This bundles server.py + jobs.py + llama_connector.py + oregano.py + all deps
(FastAPI, uvicorn, numpy) into a single executable that Tauri embeds via
externalBin. No Python installation required on the user's machine.

Usage:
    cd sidecar
    pyinstaller kamvex-sidecar.spec

Output: dist/kamvex-sidecar/kamvex-sidecar.exe
Tauri expects: src-tauri/binaries/kamvex-sidecar-x86_64-pc-windows-msvc.exe
"""

block_cipher = None

a = Analysis(
    ['server.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'fastapi.middleware.cors',
        'pydantic',
        'numpy',
        'jobs',
        'llama_connector',
        'oregano',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'transformers', 'sentence_transformers', 'sklearn', 'scipy'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='kamvex-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='kamvex-sidecar',
)
