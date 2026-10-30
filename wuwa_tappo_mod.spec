# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: 单文件窗口程序"""
import sys
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['brotli'] + collect_submodules('wuwa_tappo_mod'),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='WuwaTappoMod',
    debug=False,
    strip=False,
    upx=False,
    console=False,          # 窗口程序, 无控制台
    disable_windowed_traceback=False,
    version='version_info.txt',
)
