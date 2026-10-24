"""
generar_iconos_windows.py — Crea los iconos de los accesos directos de Windows:

    mando.ico           el mando (acceso "Iniciar")
    mando_detener.ico   el mando con una X roja (acceso "Detener")

Reutiliza el dibujo de generar_icono.py, con fondo transparente.
Uso:
    python generar_iconos_windows.py
Necesita Pillow (pip install pillow).
"""

from PIL import Image, ImageChops

import generar_icono as dibujo

LADO = 32                       # lienzo base en píxeles de pixel art
TAMANOS = (256, 128, 64, 48, 32, 24, 16)

ROJO = (214, 64, 64, 255)
ROJO_LUZ = (240, 120, 112, 255)
ROJO_OSC = (140, 36, 40, 255)
BORDE = (10, 11, 14, 255)


def mando_transparente():
    """El dibujo del mando sobre fondo transparente, centrado en un lienzo de 32 x 32."""
    rgb = dibujo.img
    fondo = Image.new("RGB", rgb.size, dibujo.C["fondo"])
    caja = ImageChops.difference(rgb, fondo).getbbox()
    recorte = rgb.crop(caja).convert("RGBA")

    px = recorte.load()
    for y in range(recorte.height):
        for x in range(recorte.width):
            r, g, b, a = px[x, y]
            if (r, g, b) == dibujo.C["fondo"]:
                px[x, y] = (0, 0, 0, 0)           # fondo -> transparente
            elif (r, g, b) == dibujo.C["sombra_bg"]:
                px[x, y] = (0, 0, 0, 80)          # sombra proyectada -> sombra suave

    lienzo = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    lienzo.paste(recorte, ((LADO - recorte.width) // 2, (LADO - recorte.height) // 2), recorte)
    return lienzo


def con_x_roja(base):
    """Añade una X roja en pixel art, abajo a la derecha, con contorno oscuro para que se lea."""
    im = base.copy()
    px = im.load()
    x0, y0, lado = 19, 19, 11          # la X ocupa x 19..29, y 19..29

    trazo = set()
    for i in range(lado):
        for grosor in (0, 1):          # trazo de 2 píxeles
            trazo.add((x0 + i + grosor, y0 + i))
            trazo.add((x0 + lado - 1 - i + grosor, y0 + i))
    trazo = {(x, y) for x, y in trazo if x < LADO and y < LADO}

    # Contorno: todo vecino del trazo que no sea trazo
    for x, y in trazo:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                v = (x + dx, y + dy)
                if v not in trazo and 0 <= v[0] < LADO and 0 <= v[1] < LADO:
                    px[v] = BORDE
    # Trazo con un poco de volumen: luz arriba, sombra abajo
    for x, y in trazo:
        if y - y0 <= 2:
            px[x, y] = ROJO_LUZ
        elif y - y0 >= lado - 3:
            px[x, y] = ROJO_OSC
        else:
            px[x, y] = ROJO
    return im


def guardar_ico(base, ruta):
    capas = []
    for t in TAMANOS:
        if t % LADO == 0:
            capas.append(base.resize((t, t), Image.NEAREST))        # escalado limpio de pixel art
        else:
            capas.append(base.resize((t, t), Image.LANCZOS))        # 48, 24 y 16: suavizado
    capas[0].save(ruta, format="ICO", sizes=[(t, t) for t in TAMANOS], append_images=capas[1:])


if __name__ == "__main__":
    mando = mando_transparente()
    guardar_ico(mando, "mando.ico")
    guardar_ico(con_x_roja(mando), "mando_detener.ico")
    print("Creados mando.ico y mando_detener.ico")
