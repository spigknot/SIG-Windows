# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files


python_runtime = Path(sys.base_prefix)
runtime_binaries = [
    (str(path), ".")
    for name in ("vcruntime140.dll", "vcruntime140_1.dll")
    for path in [python_runtime / name]
    if path.exists()
]

sounddevice_datas = collect_data_files('_sounddevice_data')

a = Analysis(
    ['src/sig_app.py'],
    pathex=[],
    binaries=runtime_binaries,
    datas=[
        ('assets/appwin.jpg', 'assets'),
        ('assets/appwin.png', 'assets'),
        ('assets/icon.png', 'assets'),
        ('assets/default_nomes.txt', 'assets'),
        ('prompts/*.txt', 'prompts'),
        ('modelos/*.docx', 'modelos'),
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
    [],
    exclude_binaries=True,
    name='sig',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Evita falhas de carregamento do python311.dll em máquinas que rejeitam
    # DLLs comprimidas ou que ainda não têm o runtime VC instalado.
    upx=False,
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

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='sig',
)
