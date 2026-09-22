"""
PyInstaller spec for building the KAMVEX Python sidecar into a standalone exe.

Bundles server.py + its modules (paths, downloads, embedding_gguf, jobs,
llama_connector, oregano, textsource) + DASA (RAG anti-hallucination) + SHARD
(vector DB) + deps (FastAPI, uvicorn, numpy, psutil, pypdf). torch and
sentence-transformers are deliberately excluded (~2 GB): embeddings in the
installer go through `llama-server --embedding` (see embedding_gguf.py).

Usage:
    cd sidecar
    pyinstaller kamvex-sidecar.spec --noconfirm

Output: dist/kamvex-sidecar.exe (onefile)
Tauri expects: src-tauri/binaries/kamvex-sidecar-x86_64-pc-windows-msvc.exe
"""

from pathlib import Path

block_cipher = None

# Resolve sibling repos (DASA-main, SHARD-main) for bundling
_HERE = Path(SPECPATH).resolve()  # sidecar/ dir
_REPOS_ROOT = _HERE.parent.parent  # "2 REPOS DASA AND SHARD/"
_DASA = str(_REPOS_ROOT / "DASA-main")
_SHARD = str(_REPOS_ROOT / "SHARD-main")

a = Analysis(
    ['server.py'],
    pathex=['.', _DASA, _SHARD],
    binaries=[],
    datas=[],
    hiddenimports=[
        # ── Sidecar modules ──
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
        'psutil',
        'pypdf',
        'paths',
        'downloads',
        'embedding_gguf',
        'jobs',
        'llama_connector',
        'oregano',
        'textsource',

        # ── DASA (RAG anti-hallucination) ──
        'dasa',
        'dasa.config',
        'dasa.pipeline',
        'dasa.agent_a',
        'dasa.agent_a.embeddings',
        'dasa.agent_a.retrieval_agent',
        'dasa.agent_a.tools',
        'dasa.agent_b',
        'dasa.agent_b.llm_connector',
        'dasa.agent_b.statistical_rewriter',
        'dasa.agent_b.synthesis_engine',

        # ── SHARD (binary DB + IVF-PQ vector index) ──
        'shard',
        'shard.cli',
        'shard.core',
        'shard.core.bloom_filter',
        'shard.core.hasher',
        'shard.core.sharding',
        'shard.index',
        'shard.index.index_builder',
        'shard.index.index_reader',
        'shard.index.ivfpq_builder',
        'shard.index.ivfpq_format',
        'shard.index.ivfpq_reader',
        'shard.index.ivf_builder',
        'shard.index.ivf_reader',
        'shard.index.tfidf_reader',
        'shard.index.tfidf_writer',
        'shard.storage',
        'shard.storage.binary_encoder',
        'shard.storage.mmap_reader',
        'shard.storage.shard_writer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'transformers', 'sentence_transformers', 'sklearn', 'scipy',
              'pytest', 'httpx', 'IPython', 'matplotlib', 'tkinter'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='kamvex-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,           # stdout/stderr go to logs/sidecar.log (Tauri spawns it without a window)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
