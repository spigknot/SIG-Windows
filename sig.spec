# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

sounddevice_datas = collect_data_files('_sounddevice_data')

a = Analysis(
    ['src/sig_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/appwin.jpg', 'assets'),
        ('assets/appwin.png', 'assets'),
        ('assets/icon.png', 'assets'),
        ('assets/default_nomes.txt', 'assets'),
    ] + sounddevice_datas,
    hiddenimports=[
        '_cffi_backend',
        '_sounddevice_data',
        'sounddevice',
        'websocket',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'silero_vad',
        'silero_vad.utils_vad',
        'silero_vad.model',
        'numpy',
        'onnxruntime',
        'torch',
        'torchaudio',
        'webrtcvad',
        'soundfile',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='sig',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
