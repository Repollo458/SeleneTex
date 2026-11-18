# This Python file uses the following encoding: utf-8

DEFAULT_TEMPLATE = "Artículo"

TEMPLATES = {
    "Artículo": r"""\documentclass[12pt, a4paper]{article}

% Fuentes e idioma (LuaLaTeX)
\usepackage{fontspec}
\usepackage[spanish]{babel}

% Márgenes
\usepackage[margin=2.5cm]{geometry}

% Paquetes comunes
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage[hidelinks]{hyperref}

\title{Título del Artículo}
\author{Autor}
\date{\today}

\begin{document}

\maketitle

\section{Introducción}
Escribe aquí el contenido de tu artículo...

\end{document}
""",

    "Informe / Reporte": r"""\documentclass[12pt, a4paper]{report}

% Fuentes e idioma (LuaLaTeX)
\usepackage{fontspec}
\usepackage[spanish]{babel}

% Márgenes
\usepackage[margin=2.5cm]{geometry}

% Paquetes comunes
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage[hidelinks]{hyperref}

\title{Título del Informe}
\author{Autor}
\date{\today}

\begin{document}

\maketitle
\tableofcontents

\chapter{Introducción}
\section{Contexto}
Escribe aquí el contenido del informe...

\end{document}
""",

    "Presentación (Beamer)": r"""\documentclass{beamer}

% Tema de la presentación
\usetheme{Madrid}

% Fuentes e idioma (LuaLaTeX)
\usepackage{fontspec}
\usepackage[spanish]{babel}

\title{Título de la Presentación}
\author{Autor}
\institute{Institución}
\date{\today}

\begin{document}

\begin{frame}
    \titlepage
\end{frame}

\begin{frame}{Índice}
    \tableofcontents
\end{frame}

\section{Introducción}
\begin{frame}{Primera Diapositiva}
    \begin{itemize}
        \item Primer punto
        \item Segundo punto
    \end{itemize}
\end{frame}

\end{document}
""",

    "Libro": r"""\documentclass[12pt, a4paper]{book}

% Fuentes e idioma (LuaLaTeX)
\usepackage{fontspec}
\usepackage[spanish]{babel}

% Márgenes
\usepackage[margin=2.5cm]{geometry}

% Paquetes comunes
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage[hidelinks]{hyperref}

\title{Título del Libro}
\author{Autor}
\date{\today}

\begin{document}

\frontmatter
\maketitle
\tableofcontents

\mainmatter
\chapter{Primer Capítulo}
Escribe aquí el contenido del capítulo...

\backmatter

\end{document}
""",

    "Documento Mínimo": r"""\documentclass[12pt, a4paper]{article}
\usepackage{fontspec}
\usepackage[spanish]{babel}

\begin{document}

Escribe aquí...

\end{document}
"""
}
