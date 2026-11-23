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

LATEX_COMMANDS = [
    # Estructura y preámbulo
    r"\documentclass{}",
    r"\usepackage{}",
    r"\newcommand{}{}",
    r"\renewcommand{}{}",
    r"\definecolor{}{}{}",
    r"\lstset{}",
    r"\title{}",
    r"\author{}",
    r"\date{\today}",
    r"\maketitle",
    r"\tableofcontents",
    r"\section{}",
    r"\subsection{}",
    r"\subsubsection{}",
    r"\chapter{}",
    r"\paragraph{}",
    r"\newpage",
    r"\clearpage",
    r"\noindent",
    r"\vspace{}",
    r"\hspace{}",
    r"\setlength{}{}",
    # Entornos
    r"\begin{}",
    r"\end{}",
    r"\begin{document}",
    r"\end{document}",
    r"\begin{abstract}",
    r"\end{abstract}",
    r"\begin{itemize}",
    r"\end{itemize}",
    r"\begin{enumerate}",
    r"\end{enumerate}",
    r"\begin{figure}[htbp]",
    r"\end{figure}",
    r"\begin{table}[htbp]",
    r"\end{table}",
    r"\begin{tabular}{}",
    r"\end{tabular}",
    r"\begin{equation}",
    r"\end{equation}",
    r"\begin{align}",
    r"\end{align}",
    r"\begin{lstlisting}",
    r"\end{lstlisting}",
    r"\begin{frame}{}",
    r"\end{frame}",
    r"\begin{bmatrix}",
    r"\end{bmatrix}",
    r"\begin{pmatrix}",
    r"\end{pmatrix}",
    r"\begin{cases}",
    r"\end{cases}",
    r"\item ",
    # Tablas y figuras
    r"\centering",
    r"\toprule",
    r"\midrule",
    r"\bottomrule",
    r"\hline",
    r"\multicolumn{}{}{}",
    r"\includegraphics[width=\textwidth]{}",
    r"\caption{}",
    r"\label{}",
    r"\ref{}",
    r"\cite{}",
    r"\input{}",
    r"\include{}",
    # Formato de texto y enlaces
    r"\textbf{}",
    r"\textit{}",
    r"\emph{}",
    r"\texttt{}",
    r"\underline{}",
    r"\textcolor{}{}",
    r"\footnote{}",
    r"\url{}",
    r"\href{}{}",
    # Matemáticas
    r"\frac{}{}",
    r"\sqrt{}",
    r"\text{}",
    r"\mathbb{}",
    r"\mathcal{}",
    r"\mathrm{}",
    r"\left(",
    r"\right)",
    r"\sum",
    r"\int",
    r"\partial",
    r"\nabla",
    r"\cdot",
    r"\times",
    r"\leq",
    r"\geq",
    r"\neq",
    r"\approx",
    r"\in",
    r"\forall",
    r"\exists",
    r"\alpha",
    r"\beta",
    r"\gamma",
    r"\delta",
    r"\lambda",
    r"\pi",
    r"\sigma",
    r"\omega",
    r"\infty",
    r"\rightarrow",
    r"\Rightarrow",
]

