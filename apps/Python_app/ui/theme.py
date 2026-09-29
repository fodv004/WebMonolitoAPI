"""
ui/theme.py
Paleta, tipografia y estilos ttk de toda la app. Solo tkinter/ttk:
se usa el tema "clam" porque es el unico de los integrados que respeta
colores de fondo en botones y encabezados de Treeview en Windows.
"""
from tkinter import font as tkfont
from tkinter import ttk

# ------------------------------------------------------------------ paleta
COLOR_FONDO = "#f1f5f9"          # fondo general de la ventana
COLOR_SUPERFICIE = "#ffffff"     # tarjetas, formularios y tabla
COLOR_BORDE = "#cbd5e1"
COLOR_PRINCIPAL = "#1e3a8a"      # barra superior y encabezados
COLOR_PRINCIPAL_HOVER = "#1e40af"
COLOR_TEXTO = "#0f172a"
COLOR_TEXTO_SUAVE = "#64748b"
COLOR_TEXTO_CLARO = "#ffffff"
COLOR_EXITO = "#16a34a"
COLOR_EXITO_HOVER = "#15803d"
COLOR_INFO = "#2563eb"           # editar (PUT)
COLOR_INFO_HOVER = "#1d4ed8"
COLOR_ADVERTENCIA = "#ea580c"    # PATCH
COLOR_ADVERTENCIA_HOVER = "#c2410c"
COLOR_PELIGRO = "#dc2626"        # eliminar, 401/403
COLOR_PELIGRO_HOVER = "#b91c1c"
COLOR_NEUTRO = "#e2e8f0"         # botones secundarios
COLOR_NEUTRO_HOVER = "#cbd5e1"
COLOR_FILA_ALTERNA = "#f8fafc"
COLOR_SELECCION = "#bfdbfe"

# ------------------------------------------------------------------ tipografia
FAMILIA = "Segoe UI"
FUENTE_TITULO = (FAMILIA, 18, "bold")
FUENTE_SUBTITULO = (FAMILIA, 13, "bold")
FUENTE_NORMAL = (FAMILIA, 10)
FUENTE_NEGRITA = (FAMILIA, 10, "bold")
FUENTE_PEQUENA = (FAMILIA, 9)

ANCHO_CAMPO = 34  # mismo ancho para todos los Entry de formularios


def _boton(style, nombre, fondo, hover, texto=COLOR_TEXTO_CLARO):
    style.configure(nombre, background=fondo, foreground=texto, font=FUENTE_NEGRITA,
                    borderwidth=0, focusthickness=0, padding=(14, 7))
    style.map(nombre,
              background=[("disabled", COLOR_NEUTRO), ("pressed", hover), ("active", hover)],
              foreground=[("disabled", COLOR_TEXTO_SUAVE)])


def tarjeta_centrada(pantalla, titulo, subtitulo=None):
    """Crea una tarjeta blanca centrada en `pantalla` (se mantiene centrada al
    redimensionar) con su titulo. Devuelve el frame donde van los campos."""
    tarjeta = ttk.Frame(pantalla, style="Card.TFrame", padding=(36, 28))
    tarjeta.place(relx=0.5, rely=0.5, anchor="center")
    ttk.Label(tarjeta, text=titulo, style="Titulo.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
    if subtitulo:
        ttk.Label(tarjeta, text=subtitulo, style="Subtitulo.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
    ttk.Frame(tarjeta, style="CardInner.TFrame", height=16).grid(row=2, column=0, columnspan=2)
    tarjeta.grid_columnconfigure(1, weight=1)
    return tarjeta


def campo(tarjeta, fila, etiqueta, variable, show=""):
    """Etiqueta alineada a la derecha + Entry de ancho uniforme."""
    ttk.Label(tarjeta, text=etiqueta, style="Card.TLabel").grid(
        row=fila, column=0, sticky="e", padx=(0, 12), pady=6)
    entrada = ttk.Entry(tarjeta, textvariable=variable, width=ANCHO_CAMPO, show=show)
    entrada.grid(row=fila, column=1, sticky="ew", pady=6)
    return entrada


def aplicar(root):
    """Configura ttk.Style una sola vez para toda la app."""
    for nombre in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(nombre).configure(family=FAMILIA, size=10)
        except Exception:
            pass
    root.configure(background=COLOR_FONDO)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=COLOR_FONDO, foreground=COLOR_TEXTO, font=FUENTE_NORMAL)
    style.configure("TFrame", background=COLOR_FONDO)
    style.configure("Card.TFrame", background=COLOR_SUPERFICIE, relief="solid", borderwidth=1)
    style.configure("CardInner.TFrame", background=COLOR_SUPERFICIE)
    style.configure("TLabel", background=COLOR_FONDO, foreground=COLOR_TEXTO, font=FUENTE_NORMAL)
    style.configure("Card.TLabel", background=COLOR_SUPERFICIE)
    style.configure("Titulo.TLabel", background=COLOR_SUPERFICIE, foreground=COLOR_PRINCIPAL, font=FUENTE_TITULO)
    style.configure("Subtitulo.TLabel", background=COLOR_SUPERFICIE, foreground=COLOR_TEXTO_SUAVE,
                    font=FUENTE_PEQUENA)
    style.configure("Error.TLabel", background=COLOR_SUPERFICIE, foreground=COLOR_PELIGRO, font=FUENTE_NORMAL)
    style.configure("Info.TLabel", background=COLOR_FONDO, foreground=COLOR_TEXTO_SUAVE, font=FUENTE_PEQUENA)

    style.configure("TEntry", fieldbackground=COLOR_SUPERFICIE, bordercolor=COLOR_BORDE,
                    lightcolor=COLOR_BORDE, darkcolor=COLOR_BORDE, padding=5)
    style.map("TEntry",
              bordercolor=[("focus", COLOR_INFO)],
              lightcolor=[("focus", COLOR_INFO)],
              fieldbackground=[("disabled", COLOR_NEUTRO)])

    _boton(style, "TButton", COLOR_NEUTRO, COLOR_NEUTRO_HOVER, texto=COLOR_TEXTO)
    _boton(style, "Primary.TButton", COLOR_PRINCIPAL, COLOR_PRINCIPAL_HOVER)
    _boton(style, "Crear.TButton", COLOR_EXITO, COLOR_EXITO_HOVER)
    _boton(style, "Editar.TButton", COLOR_INFO, COLOR_INFO_HOVER)
    _boton(style, "Patch.TButton", COLOR_ADVERTENCIA, COLOR_ADVERTENCIA_HOVER)
    _boton(style, "Eliminar.TButton", COLOR_PELIGRO, COLOR_PELIGRO_HOVER)

    style.configure("Treeview", background=COLOR_SUPERFICIE, fieldbackground=COLOR_SUPERFICIE,
                    foreground=COLOR_TEXTO, rowheight=28, borderwidth=0, font=FUENTE_NORMAL)
    style.map("Treeview",
              background=[("selected", COLOR_SELECCION)],
              foreground=[("selected", COLOR_TEXTO)])
    style.configure("Treeview.Heading", background=COLOR_PRINCIPAL, foreground=COLOR_TEXTO_CLARO,
                    font=FUENTE_NEGRITA, relief="flat", padding=(6, 6))
    style.map("Treeview.Heading", background=[("active", COLOR_PRINCIPAL_HOVER)])

    style.configure("Vertical.TScrollbar", background=COLOR_NEUTRO, troughcolor=COLOR_FONDO,
                    bordercolor=COLOR_FONDO, arrowcolor=COLOR_TEXTO_SUAVE)
    style.configure("Horizontal.TScrollbar", background=COLOR_NEUTRO, troughcolor=COLOR_FONDO,
                    bordercolor=COLOR_FONDO, arrowcolor=COLOR_TEXTO_SUAVE)
    return style
