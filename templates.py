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

# Comandos y entornos añadidos dinámicamente según los \usepackage{...} del documento
PACKAGE_COMMANDS = {
    "amsmath": [
        r"\begin{align}",
        r"\end{align}",
        r"\begin{align*}",
        r"\end{align*}",
        r"\begin{gather}",
        r"\end{gather}",
        r"\begin{multline}",
        r"\end{multline}",
        r"\begin{split}",
        r"\end{split}",
        r"\begin{cases}",
        r"\end{cases}",
        r"\begin{pmatrix}",
        r"\end{pmatrix}",
        r"\begin{bmatrix}",
        r"\end{bmatrix}",
        r"\begin{vmatrix}",
        r"\end{vmatrix}",
        r"\begin{Bmatrix}",
        r"\end{Bmatrix}",
        r"\text{}",
        r"\eqref{}",
        r"\dfrac{}{}",
        r"\tfrac{}{}",
        r"\binom{}{}",
        r"\operatorname{}",
        r"\DeclareMathOperator{}{}",
        r"\numberwithin{}{}",
        r"\substack{}",
        r"\overset{}{}",
        r"\underset{}{}",
        r"\boxed{}",
        r"\tag{}",
        r"\notag",
        r"\intertext{}",
    ],
    "amssymb": [
        r"\mathbb{}",
        r"\mathfrak{}",
        r"\therefore",
        r"\because",
        r"\blacksquare",
        r"\square",
        r"\varnothing",
        r"\leqslant",
        r"\geqslant",
        r"\lesssim",
        r"\gtrsim",
        r"\nsubseteq",
        r"\subsetneq",
        r"\mapsto",
        r"\leftrightarrow",
        r"\Leftrightarrow",
    ],
    "mathtools": [
        r"\coloneqq",
        r"\eqqcolon",
        r"\DeclarePairedDelimiter{}{}{}",
        r"\mathclap{}",
        r"\xrightarrow[]{}",
        r"\xleftarrow[]{}",
        r"\begin{dcases}",
        r"\end{dcases}",
        r"\begin{pmatrix*}[]",
        r"\end{pmatrix*}",
        r"\begin{bmatrix*}[]",
        r"\end{bmatrix*}",
        r"\shortintertext{}",
    ],
    "amsthm": [
        r"\newtheorem{}{}",
        r"\theoremstyle{}",
        r"\begin{proof}",
        r"\end{proof}",
        r"\qedhere",
    ],
    "graphicx": [
        r"\includegraphics[width=\textwidth]{}",
        r"\graphicspath{{}}",
        r"\scalebox{}{}",
        r"\rotatebox{}{}",
        r"\resizebox{}{}{}",
    ],
    "subcaption": [
        r"\begin{subfigure}[b]{0.48\textwidth}",
        r"\end{subfigure}",
        r"\begin{subtable}[b]{0.48\textwidth}",
        r"\end{subtable}",
        r"\subcaption{}",
        r"\subref{}",
    ],
    "float": [
        r"\begin{figure}[H]",
        r"\begin{table}[H]",
        r"\floatplacement{}{}",
    ],
    "wrapfig": [
        r"\begin{wrapfigure}{r}{0.4\textwidth}",
        r"\end{wrapfigure}",
    ],
    "booktabs": [
        r"\toprule",
        r"\midrule",
        r"\bottomrule",
        r"\cmidrule(lr){}",
        r"\addlinespace",
        r"\morecmidrules",
    ],
    "multirow": [
        r"\multirow{}{}{}",
    ],
    "tabularx": [
        r"\begin{tabularx}{\textwidth}{}",
        r"\end{tabularx}",
    ],
    "longtable": [
        r"\begin{longtable}{}",
        r"\end{longtable}",
        r"\endhead",
        r"\endfirsthead",
        r"\endfoot",
        r"\endlastfoot",
    ],
    "array": [
        r"\newcolumntype{}{}",
        r"\extrarowheight",
    ],
    "colortbl": [
        r"\rowcolor{}",
        r"\columncolor{}",
        r"\cellcolor{}",
    ],
    "xcolor": [
        r"\textcolor{}{}",
        r"\color{}",
        r"\colorbox{}{}",
        r"\fcolorbox{}{}{}",
        r"\definecolor{}{}{}",
        r"\colorlet{}{}",
        r"\pagecolor{}",
    ],
    "hyperref": [
        r"\href{}{}",
        r"\url{}",
        r"\hyperref[]{}",
        r"\autoref{}",
        r"\nameref{}",
        r"\hypersetup{}",
        r"\texorpdfstring{}{}",
    ],
    "cleveref": [
        r"\cref{}",
        r"\Cref{}",
        r"\crefrange{}{}",
        r"\cpageref{}",
    ],
    "geometry": [
        r"\geometry{}",
        r"\newgeometry{}",
        r"\restoregeometry",
    ],
    "fontspec": [
        r"\setmainfont{}",
        r"\setsansfont{}",
        r"\setmonofont{}",
        r"\newfontfamily{}{}",
        r"\defaultfontfeatures{}",
    ],
    "babel": [
        r"\selectlanguage{}",
        r"\foreignlanguage{}{}",
        r"\begin{otherlanguage}{}",
        r"\end{otherlanguage}",
    ],
    "polyglossia": [
        r"\setmainlanguage{}",
        r"\setotherlanguage{}",
        r"\textenglish{}",
    ],
    "listings": [
        r"\begin{lstlisting}",
        r"\end{lstlisting}",
        r"\lstinline||",
        r"\lstinputlisting{}",
        r"\lstset{}",
        r"\lstdefinestyle{}{}",
    ],
    "minted": [
        r"\begin{minted}{}",
        r"\end{minted}",
        r"\mintinline{}{}",
        r"\inputminted{}{}",
        r"\setminted{}",
    ],
    "tikz": [
        r"\begin{tikzpicture}",
        r"\end{tikzpicture}",
        r"\usetikzlibrary{}",
        r"\tikzset{}",
        r"\draw ",
        r"\fill ",
        r"\filldraw ",
        r"\path ",
        r"\node ",
        r"\coordinate ",
        r"\foreach ",
        r"\begin{scope}",
        r"\end{scope}",
    ],
    "pgfplots": [
        r"\begin{axis}",
        r"\end{axis}",
        r"\addplot ",
        r"\addlegendentry{}",
        r"\pgfplotsset{}",
    ],
    "siunitx": [
        r"\qty{}{}",
        r"\num{}",
        r"\unit{}",
        r"\ang{}",
        r"\qtyrange{}{}{}",
        r"\numrange{}{}",
        r"\sisetup{}",
    ],
    "physics": [
        r"\dv{}{}",
        r"\pdv{}{}",
        r"\grad",
        r"\div",
        r"\curl",
        r"\abs{}",
        r"\norm{}",
        r"\eval{}",
        r"\bra{}",
        r"\ket{}",
        r"\braket{}{}",
        r"\mqty()",
    ],
    "algorithm2e": [
        r"\begin{algorithm}[H]",
        r"\end{algorithm}",
        r"\KwData{}",
        r"\KwResult{}",
        r"\If{}{}",
        r"\eIf{}{}{}",
        r"\For{}{}",
        r"\While{}{}",
        r"\Return{}",
    ],
    "algpseudocode": [
        r"\begin{algorithmic}",
        r"\end{algorithmic}",
        r"\State ",
        r"\If{}",
        r"\Else",
        r"\EndIf",
        r"\For{}",
        r"\EndFor",
        r"\While{}",
        r"\EndWhile",
        r"\Function{}{}",
        r"\EndFunction",
        r"\Return ",
    ],
    "biblatex": [
        r"\addbibresource{}",
        r"\printbibliography",
        r"\parencite{}",
        r"\textcite{}",
        r"\autocite{}",
        r"\footcite{}",
        r"\nocite{}",
    ],
    "natbib": [
        r"\citep{}",
        r"\citet{}",
        r"\citeauthor{}",
        r"\citeyear{}",
        r"\bibliographystyle{}",
        r"\bibliography{}",
    ],
    "tcolorbox": [
        r"\begin{tcolorbox}[]",
        r"\end{tcolorbox}",
        r"\newtcolorbox{}{}",
        r"\tcbset{}",
        r"\tcblower",
    ],
    "enumitem": [
        r"\setlist{}",
        r"\newlist{}{}{}",
    ],
    "fancyhdr": [
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        r"\fancyhead[]{}",
        r"\fancyfoot[]{}",
        r"\lhead{}",
        r"\chead{}",
        r"\rhead{}",
        r"\lfoot{}",
        r"\cfoot{}",
        r"\rfoot{}",
        r"\renewcommand{\headrulewidth}{}",
    ],
    "setspace": [
        r"\singlespacing",
        r"\onehalfspacing",
        r"\doublespacing",
        r"\setstretch{}",
    ],
    "todonotes": [
        r"\todo{}",
        r"\missingfigure{}",
        r"\listoftodos",
    ],
    "lipsum": [
        r"\lipsum[]",
    ],
    "soul": [
        r"\hl{}",
        r"\st{}",
        r"\ul{}",
        r"\caps{}",
    ],
    "ulem": [
        r"\sout{}",
        r"\uwave{}",
        r"\uline{}",
    ],
    "mhchem": [
        r"\ce{}",
    ],
    "chemfig": [
        r"\chemfig{}",
        r"\schemestart",
        r"\schemestop",
        r"\arrow",
    ],
    # Clase de documento beamer (se detecta por \documentclass{beamer})
    "beamer": [
        r"\begin{frame}{}",
        r"\end{frame}",
        r"\begin{block}{}",
        r"\end{block}",
        r"\begin{alertblock}{}",
        r"\end{alertblock}",
        r"\begin{exampleblock}{}",
        r"\end{exampleblock}",
        r"\begin{columns}",
        r"\end{columns}",
        r"\column{}",
        r"\pause",
        r"\alert{}",
        r"\usetheme{}",
        r"\usecolortheme{}",
        r"\frametitle{}",
        r"\framesubtitle{}",
        r"\institute{}",
    ],
}

