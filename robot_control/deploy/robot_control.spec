import os
import sys
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).parent.parent
FRONTEND_DIST = str(PROJECT_ROOT / "robot_control" / "frontend" / "dist")
SHARED_SRC = str(PROJECT_ROOT / "shared" / "src")
BACKEND_APP = str(PROJECT_ROOT / "robot_control" / "backend")

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
        'app.api.arm',
        'app.api.navigation',
        'app.api.ros2_nodes',
        'app.ws.status',
        'app.ws.logs',
        'app.services.robot_service',
        'app.services.arm_service',
        'app.services.status_service',
        'app.services.log_service',
        'app.services.ros2_manager',
        'app.ros2.service_client',
        'app.ros2.log_collector',
        'app.core.config',
        'app.models.teach',
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
    name='robot_control_server',
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
    name='robot_control',
)
