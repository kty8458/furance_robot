import os
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).parent.parent
FRONTEND_DIST = str(PROJECT_ROOT / "dispatch" / "frontend" / "dist")
SHARED_SRC = str(PROJECT_ROOT / "shared" / "src")
BACKEND_APP = str(PROJECT_ROOT / "dispatch" / "backend")

a = Analysis(
    [os.path.join(SPECPATH, 'start_server.py')],
    pathex=[BACKEND_APP, SHARED_SRC],
    binaries=[],
    datas=[
        (FRONTEND_DIST, 'static'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'app.main',
        'app.api.robot',
        'app.api.navigation',
        'app.api.task',
        'app.api.sampler',
        'app.api.status',
        'app.services.robot_proxy',
        'app.services.status_service',
        'app.services.task_engine',
        'app.services.sampler_service',
        'app.services.l2_listener',
        'app.clients.robot_http',
        'app.clients.robot_ws',
        'app.clients.sampler_ws',
        'app.clients.l2_client',
        'app.core.config',
        'app.core.database',
        'furance_shared',
        'furance_shared.models',
        'furance_shared.models.robot',
        'furance_shared.models.command',
        'furance_shared.models.status',
        'furance_shared.protocol',
        'furance_shared.protocol.http_schema',
        'furance_shared.protocol.ws_frames',
        'furance_shared.utils',
        'furance_shared.utils.errors',
        'furance_shared.utils.logging',
        'pydantic',
        'pydantic_settings',
        'aiosqlite',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='dispatch_server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='dispatch',
)
