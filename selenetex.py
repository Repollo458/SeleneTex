#!/usr/bin/env python3
# This Python file uses the following encoding: utf-8
"""Punto de entrada principal de SeleneTeX.

Uso:
    python selenetex.py
    python selenetex.py mi_documento.tex
    python selenetex.py ruta/a/proyecto/
"""

import sys

from mainwindow import main

if __name__ == "__main__":
    sys.exit(main())
