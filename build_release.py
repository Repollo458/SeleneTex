#!/usr/bin/env python3
# This Python file uses the following encoding: utf-8
"""Script auxiliar para empaquetar SeleneTeX como ejecutable independiente con PyInstaller.

Uso:
    pip install pyinstaller
    python build_release.py            # Genera carpeta dist/SeleneTeX/ (arranque rápido)
    python build_release.py --onefile  # Genera un único binario en dist/
"""

import argparse
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
DATA_SEP = ";" if os.name == "nt" else ":"

EXCLUDED_MODULES = [
    "tkinter",
    "matplotlib",
    "numpy",
    "scipy",
    "pandas",
    "PIL",
    "torch",
    "tensorflow",
    "keras",
    "cv2",
    "pytest",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtGraphs",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Empaqueta SeleneTeX con PyInstaller.")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Empaquetar en un único archivo ejecutable (ideal para subir a GitHub Releases).",
    )
    args = parser.parse_args()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "SeleneTeX",
        "--hidden-import",
        "pymupdf",
        "--add-data",
        f"{ROOT / 'logo.png'}{DATA_SEP}.",
        "--onefile" if args.onefile else "--onedir",
    ]

    for mod in EXCLUDED_MODULES:
        cmd.extend(["--exclude-module", mod])

    if sys.platform in ("win32", "darwin") and (ROOT / "logo.png").exists():
        cmd.extend(["--icon", str(ROOT / "logo.png")])

    cmd.append(str(ROOT / "selenetex.py"))

    print("Ejecutando:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    sys.exit(main())
