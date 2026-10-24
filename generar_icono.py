"""
generar_icono.py — Dibuja el icono del mando (pixel art en lienzo de 45 x 45, escalado a 180 x 180).

Uso:
    python generar_icono.py icono.png
Luego convierte icono.png a base64 y pégalo en ICONO_PNG de apagar_pc.py.
Los iconos de Windows (.ico) se generan con generar_iconos_windows.py, que reutiliza este dibujo.
Necesita Pillow (pip install pillow).
"""

import math
import sys

from PIL import Image

N = 30          # lienzo de dibujo
FINAL = 45      # lienzo final: el dibujo se centra con margen generoso alrededor
ESCALA = 4      # 45 x 4 = 180 px, el tamaño de apple-touch-icon

C = {
    "fondo":     (28, 31, 36),
    "sombra_bg": (21, 23, 27),
    "contorno":  (10, 11, 14),
    "cuerpo":    (58, 63, 72),
    "brillo":    (86, 93, 106),
    "brillo2":   (70, 76, 87),
    "sombra":    (42, 46, 53),
    "sombra2":   (34, 37, 43),
    "ir":        (16, 17, 20),
    "ir_brillo": (66, 72, 84),
    "rojo":      (196, 82, 82),
    "rojo_luz":  (232, 136, 128),
    "rojo_osc":  (120, 50, 50),
    "gris":      (150, 157, 168),
    "gris_luz":  (188, 193, 201),
    "gris_osc":  (98, 104, 115),
    "azul":      (88, 136, 214),
    "azul_luz":  (138, 176, 236),
    "azul_osc":  (48, 78, 126),
    "ok":        (31, 53, 86),
    "ok_luz":    (52, 84, 132),
    "ranura":    (30, 33, 39),
    "onda1":     (88, 136, 214),
    "onda2":     (50, 82, 132),
}

img = Image.new("RGB", (N, N), C["fondo"])
px = img.load()


def pon(x, y, color):
    if 0 <= x < N and 0 <= y < N:
        px[x, y] = C[color]


def rect(x0, y0, x1, y1, color):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            pon(x, y, color)


# Cuerpo del mando: x 9..20, y 7..27
X0, X1, Y0, Y1 = 9, 20, 7, 27

# Sombra proyectada (abajo a la derecha)
rect(X0 + 1, Y0 + 1, X1 + 1, Y1 + 1, "sombra_bg")
pon(X1 + 1, Y0 + 1, "fondo"); pon(X0 + 1, Y1 + 1, "fondo")

# Contorno con esquinas redondeadas
rect(X0, Y0, X1, Y1, "contorno")
for x, y in ((X0, Y0), (X1, Y0), (X0, Y1), (X1, Y1)):
    pon(x, y, "fondo" if (x, y) != (X1, Y1) else "sombra_bg")

# Relleno y biselado
rect(X0 + 1, Y0 + 1, X1 - 1, Y1 - 1, "cuerpo")
for x, y in ((X0 + 1, Y0 + 1), (X1 - 1, Y0 + 1), (X0 + 1, Y1 - 1), (X1 - 1, Y1 - 1)):
    pon(x, y, "contorno")
for y in range(Y0 + 2, Y1 - 1):
    pon(X0 + 1, y, "brillo")
    pon(X0 + 2, y, "brillo2")
    pon(X1 - 1, y, "sombra")
for x in range(X0 + 2, X1 - 1):
    pon(x, Y0 + 1, "brillo")
    pon(x, Y1 - 1, "sombra2")
pon(X1 - 1, Y1 - 2, "sombra2")

# Ventana del infrarrojo
rect(13, 9, 16, 9, "ir")
pon(13, 9, "ir_brillo")

# Botón de encendido (derecha) y botón gris (izquierda)
rect(17, 11, 18, 12, "rojo"); pon(17, 11, "rojo_luz"); pon(18, 12, "rojo_osc")
rect(12, 11, 13, 12, "gris"); pon(12, 11, "gris_luz"); pon(13, 12, "gris_osc")

# Cruceta circular con botón OK
cx, cy = 15.0, 17.0
for y in range(12, 22):
    for x in range(10, 20):
        dx, dy = x + 0.5 - cx, y + 0.5 - cy
        d = math.hypot(dx, dy)
        if d <= 1.5:
            pon(x, y, "ok_luz" if dx < 0 and dy < 0 else "ok")
        elif d <= 2.2:
            pon(x, y, "ranura")
        elif d <= 3.5:
            if dx + dy < -2.0:
                pon(x, y, "azul_luz")
            elif dx + dy > 2.0:
                pon(x, y, "azul_osc")
            else:
                pon(x, y, "azul")
        elif d <= 4.1 and dx + dy > 0.5:
            pon(x, y, "sombra2")

# Dos filas de teclas (con su sombra debajo)
for fila in (22, 24):
    for x0 in (11, 14, 17):
        pon(x0, fila, "gris_luz"); pon(x0 + 1, fila, "gris")
        pon(x0, fila + 1, "gris_osc"); pon(x0 + 1, fila + 1, "gris_osc")

# Ondas de señal sobre el mando, dibujadas a mano.
# La fila 6 queda libre para que no rocen el mando, y arriba hay margen hasta el borde.
for x in range(12, 18):
    pon(x, 2, "onda2")                     # onda exterior: tramo superior
for x in (10, 11, 18, 19):
    pon(x, 3, "onda2")                     # onda exterior: laterales
for x in range(13, 17):
    pon(x, 4, "onda1")                     # onda interior: tramo superior
for x in (12, 17):
    pon(x, 5, "onda1")                     # onda interior: laterales


def icono_png(ruta):
    """Icono para el iPhone: dibujo centrado sobre fondo oscuro, 180 x 180."""
    from PIL import ImageChops
    fondo = Image.new("RGB", img.size, C["fondo"])
    x0, y0, x1, y1 = ImageChops.difference(img, fondo).getbbox()
    final = Image.new("RGB", (FINAL, FINAL), C["fondo"])
    final.paste(img.crop((x0, y0, x1, y1)), ((FINAL - (x1 - x0)) // 2, (FINAL - (y1 - y0)) // 2))
    grande = final.resize((FINAL * ESCALA, FINAL * ESCALA), Image.NEAREST)
    grande = grande.convert("P", palette=Image.ADAPTIVE, colors=32)
    grande.save(ruta, optimize=True)


if __name__ == "__main__":
    icono_png(sys.argv[1] if len(sys.argv) > 1 else "icono.png")
