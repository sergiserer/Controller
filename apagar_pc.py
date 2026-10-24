"""
apagar_pc.py — Controla tu PC Windows desde el móvil, dentro de tu red local:
apagar, reiniciar, temporizador de apagado, cancelar, volumen (subir, bajar, silenciar)
y brillo del monitor (DDC/CI).

Uso:
    python apagar_pc.py          (con ventana de consola, para probar)
    pythonw apagar_pc.py         (sin ventana, para el arranque automático)

La primera vez genera un token secreto y te muestra la URL que tienes que abrir en el iPhone.
Solo usa la librería estándar de Python: no hace falta instalar nada.
"""

import base64
import ctypes
import hmac
import json
import secrets
import socket
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PUERTO = 8765
SEGUNDOS_AVISO = 7  # margen para cancelar el apagado
# Carpeta base: junto al .exe si está empaquetado (PyInstaller), si no junto a este .py.
# Así el token.txt se conserva entre arranques y la URL del móvil no cambia.
if getattr(sys, "frozen", False):
    CARPETA_BASE = Path(sys.executable).parent
else:
    CARPETA_BASE = Path(__file__).parent
FICHERO_TOKEN = CARPETA_BASE / "token.txt"

TEMPORIZADOR_MIN = 60              # 1 minuto
TEMPORIZADOR_MAX = 23 * 3600 + 59 * 60   # 23 h 59 min

# Lo que hay programado ahora mismo. La cuenta atrás la lleva este programa, no Windows:
# así Windows no muestra su aviso de "se ha programado un apagado", que tapa la pantalla.
# Al llegar a cero se lanza "shutdown /t 0", que apaga en el acto sin ningún aviso.
_programado = None   # {"tipo": "apagar" | "reiniciar" | "temporizador", "fin": instante}
_lock_programado = threading.Lock()


def programar(tipo: str, segundos: int) -> bool:
    """Programa la acción. Devuelve False si ya había otra en marcha."""
    global _programado
    with _lock_programado:
        if _programado is not None:
            return False
        _programado = {"tipo": tipo, "fin": time.time() + segundos}
        return True


def desprogramar() -> bool:
    """Anula lo programado. Devuelve True si había algo."""
    global _programado
    with _lock_programado:
        habia = _programado is not None
        _programado = None
        return habia


def consultar_programado():
    """Devuelve (tipo, segundos_restantes) o None."""
    with _lock_programado:
        if _programado is None:
            return None
        return _programado["tipo"], max(0, round(_programado["fin"] - time.time()))


def vigilante() -> None:
    """Hilo en segundo plano: comprueba cada segundo si ha llegado la hora.
    Usa la hora real, así que también funciona si el PC estuvo suspendido."""
    global _programado
    while True:
        time.sleep(1)
        with _lock_programado:
            if _programado is None or time.time() < _programado["fin"]:
                continue
            tipo = _programado["tipo"]
            _programado = None
        # /f cierra las aplicaciones abiertas sin esperar (igual que hacía "shutdown /t" con tiempo)
        ejecutar(["shutdown", "/r" if tipo == "reiniciar" else "/s", "/f", "/t", "0"])


def ejecutar(comando) -> bool:
    resultado = subprocess.run(comando, capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    return resultado.returncode == 0

# ---------------------------------------------------------------- Volumen
# Teclas multimedia virtuales de Windows (cada pulsación = 2 % de volumen)
TECLAS_VOLUMEN = {
    "subir":    0xAF,  # VK_VOLUME_UP
    "bajar":    0xAE,  # VK_VOLUME_DOWN
    "silencio": 0xAD,  # VK_VOLUME_MUTE
}
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


def pulsar_tecla(vk: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


# ---------------------------------------------------------------- Brillo (DDC/CI)
# Mismo mecanismo que usa Twinkle Tray: el código VCP 0x10 es el brillo del monitor.
VCP_BRILLO = 0x10


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [("hPhysicalMonitor", wintypes.HANDLE),
                ("szPhysicalMonitorDescription", wintypes.WCHAR * 128)]


_user32 = ctypes.windll.user32
_dxva2 = ctypes.windll.dxva2

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
_user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, _ENUM_PROC, wintypes.LPARAM]
_dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
_dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
_dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [wintypes.HANDLE, wintypes.BYTE, ctypes.c_void_p,
                                                   ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
_dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
_dxva2.DestroyPhysicalMonitor.argtypes = [wintypes.HANDLE]

_lock_ddc = threading.Lock()   # el bus DDC no admite órdenes simultáneas
_maximos = {}                  # valor máximo de brillo de cada monitor (normalmente 100)


def _monitores_fisicos():
    hmons = []

    def recoger(hmon, hdc, rect, datos):
        hmons.append(hmon)
        return True

    callback = _ENUM_PROC(recoger)
    _user32.EnumDisplayMonitors(None, None, callback, 0)

    fisicos = []
    for hmon in hmons:
        n = wintypes.DWORD()
        if not _dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or n.value == 0:
            continue
        lista = (PHYSICAL_MONITOR * n.value)()
        if _dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, lista):
            fisicos.extend(lista)
    return fisicos


def _liberar(monitores):
    for m in monitores:
        _dxva2.DestroyPhysicalMonitor(m.hPhysicalMonitor)


def _leer_vcp(handle):
    actual, maximo = wintypes.DWORD(), wintypes.DWORD()
    if _dxva2.GetVCPFeatureAndVCPFeatureReply(handle, VCP_BRILLO, None,
                                              ctypes.byref(actual), ctypes.byref(maximo)):
        return actual.value, maximo.value
    return None


def leer_brillo():
    """Devuelve el brillo (0-100) del primer monitor que responda, o None."""
    with _lock_ddc:
        monitores = _monitores_fisicos()
        try:
            for i, m in enumerate(monitores):
                r = _leer_vcp(m.hPhysicalMonitor)
                if r and r[1] > 0:
                    _maximos[i] = r[1]
                    return round(r[0] * 100 / r[1])
            return None
        finally:
            _liberar(monitores)


def fijar_brillo(porcentaje: int) -> bool:
    """Aplica el brillo a todos los monitores compatibles con DDC/CI."""
    with _lock_ddc:
        monitores = _monitores_fisicos()
        try:
            alguno = False
            for i, m in enumerate(monitores):
                if i not in _maximos:
                    r = _leer_vcp(m.hPhysicalMonitor)
                    _maximos[i] = r[1] if r and r[1] > 0 else 100
                valor = round(porcentaje * _maximos[i] / 100)
                if _dxva2.SetVCPFeature(m.hPhysicalMonitor, VCP_BRILLO, valor):
                    alguno = True
            return alguno
        finally:
            _liberar(monitores)


# ---------------------------------------------------------------- Icono
# Mando a distancia en pixel art (180 x 180 PNG). Se genera con generar_icono.py.
# Si lo cambias, sube VERSION_ICONO para que el iPhone no use el de su caché.
VERSION_ICONO = "3"
ICONO_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAALQAAAC0CAMAAAAKE/YAAAAARVBMVEW8wcmKsOzoiICWnahYiNZiaHNWXWrEUlJG"
    "TFc0VIQyUoQwTn54MjJCSFQ6P0gqLjUfNVYiJSseISccHyQVFxsQERQKCw7gSCG8AAABUUlEQVR42u3ZSW7CQBBA"
    "UWcgEwngxMn9j5oqyZYsBJhIBLnM+6uW1Yu36sHdfBWsgYaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGXjD67UjQ0NXQ"
    "U7hL46Ghr7m5PO5VYkeEhj4BPucbNHQVtJsL9FLQP2cGDV0BPYCeJrokHBr6v9GJeok20Uf0PWrTt41ybhdBQ1dC"
    "HwsauiK6iR6iMfY+eo6goSuiE7yKxugEv0fQ0BXRdkToJaLv+oaHImjoyujEfu6V8DaChq6Mfo12ETR0dXQCE7rr"
    "y/E6goaujh4HDV0ZnYf94fC/7kvw7G8u0NAn0O1eJW7j0ND+mkLfAHr88HloDA1dDb3qS+ihMTR0NbTVA/rW1um8"
    "EEBDV0Fn7UTDPGjouaPH8Km6PmjouaOz7g9BQ1dAXzNoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaOiZ9QvXOgcI8tD4"
    "GgAAAABJRU5ErkJggg=="
)


# ---------------------------------------------------------------- Utilidades
def cargar_token() -> str:
    if FICHERO_TOKEN.exists():
        return FICHERO_TOKEN.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(16)
    FICHERO_TOKEN.write_text(token, encoding="utf-8")
    return token


TOKEN = cargar_token()


def ip_local() -> str:
    # Truco habitual: "conectar" un socket UDP (no envía nada) para saber qué IP usa el PC en la LAN.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.1.1", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Mi PC">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#1c1f24">
<link rel="apple-touch-icon" href="/icono.png?v=__VERSION_ICONO__">
<link rel="icon" type="image/png" href="/icono.png?v=__VERSION_ICONO__">
<title>Mi PC</title>
<style>
  :root {
    --fondo:  #1c1f24;
    --luz:    #272b32;
    --sombra: #121418;
    --texto:  #c9ced6;
    --tenue:  #6b7380;
    --azul:   #4a78c2;
    --azul-profundo: #1f3556;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body { margin: 0; height: 100%; background: var(--fondo); }
  body {
    min-height: 100vh;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: calc(env(safe-area-inset-top) + 28px) 28px calc(env(safe-area-inset-bottom) + 28px);
    color: var(--texto);
    font-family: -apple-system, "SF Pro Display", "Helvetica Neue", system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
    -webkit-user-select: none; user-select: none; -webkit-touch-callout: none;
  }
  button { touch-action: manipulation; }

  header { text-align: center; margin-bottom: 44px; }
  .etiqueta {
    font-size: 11px; letter-spacing: .32em; text-transform: uppercase; color: var(--tenue);
    display: inline-flex; align-items: center; gap: 10px;
  }
  .punto {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--azul); box-shadow: 0 0 8px var(--azul);
  }
  h1 { margin: 12px 0 0; font-weight: 200; font-size: 30px; letter-spacing: .06em; }

  /* Botón principal: relieve neomórfico */
  .encendido {
    width: 176px; height: 176px; border: 0; border-radius: 50%; padding: 0;
    background: var(--fondo);
    box-shadow: 14px 14px 30px var(--sombra), -14px -14px 30px var(--luz);
    display: grid; place-items: center; cursor: pointer;
    transition: box-shadow .25s ease;
  }
  .encendido .anillo {
    width: 126px; height: 126px; border-radius: 50%;
    display: grid; place-items: center;
    background: linear-gradient(145deg, #1a1d21, #20242a);
    box-shadow: inset 6px 6px 12px var(--sombra), inset -6px -6px 12px var(--luz);
    transition: background .4s ease;
  }
  .encendido svg {
    width: 42px; height: 42px; stroke: var(--tenue);
    transition: stroke .4s ease, filter .4s ease;
  }
  .encendido:active {
    box-shadow: inset 10px 10px 22px var(--sombra), inset -10px -10px 22px var(--luz);
  }
  .encendido.activo .anillo { background: linear-gradient(145deg, #1a2333, var(--azul-profundo)); }
  .encendido.activo svg { stroke: var(--azul); filter: drop-shadow(0 0 6px rgba(74,120,194,.6)); }

  /* Volumen: carril hundido con botones en relieve */
  .volumen { margin-top: 48px; width: 100%; max-width: 340px; }
  .mando {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px; border-radius: 44px;
    box-shadow: inset 6px 6px 12px var(--sombra), inset -6px -6px 12px var(--luz);
  }
  .redondo {
    width: 62px; height: 62px; border: 0; border-radius: 50%; padding: 0;
    background: var(--fondo); display: grid; place-items: center; cursor: pointer;
    box-shadow: 6px 6px 12px var(--sombra), -6px -6px 12px var(--luz);
    transition: box-shadow .15s ease;
  }
  .redondo.pequeno { width: 48px; height: 48px; }
  .redondo svg {
    width: 22px; height: 22px; stroke: var(--texto); fill: none;
    stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round;
    transition: stroke .15s ease, filter .3s ease;
  }
  .redondo.pequeno svg { width: 19px; height: 19px; stroke: var(--tenue); }
  .redondo:active {
    box-shadow: inset 4px 4px 9px var(--sombra), inset -4px -4px 9px var(--luz);
  }
  .redondo:active svg { stroke: var(--azul); }

  /* Botones de las esquinas: reloj (izquierda) y sol (derecha) */
  .esquina { position: fixed; z-index: 3; top: calc(env(safe-area-inset-top) + 18px); }
  .esquina.izq { left: 20px; }
  .esquina.der { right: 20px; }
  .esquina.abierto {
    z-index: 6;
    box-shadow: inset 4px 4px 9px var(--sombra), inset -4px -4px 9px var(--luz);
  }
  .esquina.abierto svg { stroke: var(--azul); }
  .esquina.activo svg { stroke: var(--azul); filter: drop-shadow(0 0 5px rgba(74,120,194,.7)); }

  /* Velo: mientras hay un panel abierto, bloquea todo lo demás */
  .velo {
    position: fixed; inset: 0; z-index: 4;
    background: rgba(10, 11, 14, .45);
    opacity: 0; pointer-events: none; transition: opacity .25s ease;
  }
  .velo.visible { opacity: 1; pointer-events: auto; }

  /* Paneles desplegables */
  .panel {
    position: fixed; z-index: 5;
    top: calc(env(safe-area-inset-top) + 82px); left: 20px; right: 20px;
    max-width: 420px;
    padding: 24px 22px; border-radius: 26px; background: var(--fondo);
    box-shadow: 12px 12px 28px var(--sombra), -12px -12px 28px var(--luz);
    opacity: 0; transform: translateY(-10px); pointer-events: none;
    transition: opacity .25s ease, transform .25s ease;
  }
  .panel.der { margin-left: auto; }
  .panel.izq { margin-right: auto; }
  .panel.visible { opacity: 1; transform: none; pointer-events: auto; }
  .aviso { margin-top: 14px; font-size: 12px; color: var(--tenue); text-align: center; line-height: 1.5; }
  .aviso:empty { display: none; }

  /* Brillo */
  .fila { display: flex; align-items: center; gap: 18px; }
  .pct {
    width: 36px; text-align: right; font-size: 14px; font-weight: 300;
    font-variant-numeric: tabular-nums; color: var(--texto);
  }
  input[type=range] {
    -webkit-appearance: none; appearance: none;
    flex: 1; height: 16px; margin: 0; background: transparent; --p: 50%;
  }
  input[type=range]:focus { outline: none; }
  input[type=range]::-webkit-slider-runnable-track {
    height: 16px; border-radius: 8px;
    background-color: var(--fondo);
    background-image: linear-gradient(90deg, var(--azul-profundo), var(--azul));
    background-size: var(--p) 100%; background-repeat: no-repeat;
    box-shadow: inset 3px 3px 7px var(--sombra), inset -3px -3px 7px var(--luz);
  }
  input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none;
    width: 30px; height: 30px; margin-top: -7px; border-radius: 50%;
    background: var(--fondo);
    box-shadow: 4px 4px 9px var(--sombra), -4px -4px 9px var(--luz);
  }
  input[type=range]:disabled { opacity: .4; }

  /* Temporizador: dos casillas hundidas (horas y minutos) */
  .selector { display: flex; align-items: center; gap: 12px; }
  .caja {
    position: relative; flex: 1; height: 100px; border-radius: 20px;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
    box-shadow: inset 5px 5px 11px var(--sombra), inset -5px -5px 11px var(--luz);
  }
  .caja .num {
    font-size: 40px; font-weight: 200; line-height: 1;
    font-variant-numeric: tabular-nums; color: var(--texto);
  }
  .caja .unidad { font-size: 10px; letter-spacing: .28em; text-transform: uppercase; color: var(--tenue); }
  .caja select {
    position: absolute; inset: 0; width: 100%; height: 100%;
    opacity: 0; font-size: 16px; border: 0; cursor: pointer;
    -webkit-appearance: none; appearance: none;
  }
  .dos-puntos { font-size: 30px; font-weight: 200; color: var(--tenue); margin-bottom: 18px; }
  .atajos { display: flex; gap: 10px; margin-top: 20px; }
  .chip {
    flex: 1; padding: 11px 0; border: 0; border-radius: 12px;
    background: var(--fondo); color: var(--tenue);
    font: inherit; font-size: 11px; letter-spacing: .06em; cursor: pointer;
    box-shadow: 4px 4px 9px var(--sombra), -4px -4px 9px var(--luz);
    transition: box-shadow .15s ease, color .15s ease;
  }
  .chip:active {
    box-shadow: inset 3px 3px 7px var(--sombra), inset -3px -3px 7px var(--luz);
    color: var(--azul);
  }
  .programar {
    display: block; width: 100%; margin-top: 22px; padding: 18px 0; border: 0; border-radius: 16px;
    background: linear-gradient(145deg, #25426d, #1a2f4f); color: #dbe4f2;
    font: inherit; font-size: 12px; font-weight: 500; letter-spacing: .18em; text-transform: uppercase;
    box-shadow: 6px 6px 14px var(--sombra), -6px -6px 14px var(--luz);
    transition: box-shadow .15s ease, opacity .2s ease; cursor: pointer;
  }
  .programar:active {
    box-shadow: inset 5px 5px 10px rgba(0,0,0,.45), inset -3px -3px 8px rgba(255,255,255,.04);
  }
  .programar:disabled { opacity: .35; }

  /* Botones secundarios */
  .acciones { display: flex; gap: 22px; margin-top: 36px; width: 100%; max-width: 340px; }
  .btn {
    flex: 1; padding: 19px 0; border: 0; border-radius: 18px;
    background: var(--fondo); color: var(--texto);
    font: inherit; font-size: 12px; font-weight: 500;
    letter-spacing: .18em; text-transform: uppercase;
    box-shadow: 8px 8px 18px var(--sombra), -8px -8px 18px var(--luz);
    transition: box-shadow .15s ease, color .15s ease; cursor: pointer;
  }
  .btn:active {
    box-shadow: inset 6px 6px 12px var(--sombra), inset -6px -6px 12px var(--luz);
    color: var(--azul);
  }

  .estado {
    margin-top: 32px; min-height: 20px; text-align: center;
    font-size: 13px; letter-spacing: .04em; color: var(--tenue);
  }
  .estado b { color: var(--azul); font-weight: 500; font-variant-numeric: tabular-nums; }
  .nota {
    margin-top: 8px; min-height: 16px; text-align: center;
    font-size: 12px; color: var(--tenue); opacity: .8;
  }
</style>
</head>
<body>
  <!-- Reloj (temporizador), arriba a la izquierda -->
  <button id="reloj" class="redondo pequeno esquina izq" aria-label="Temporizador">
    <svg viewBox="0 0 24 24">
      <circle cx="12" cy="13" r="8"/>
      <path d="M12 9v4l2.5 2"/>
      <path d="M10 2.5h4"/>
    </svg>
  </button>

  <!-- Sol (brillo), arriba a la derecha -->
  <button id="sol" class="redondo pequeno esquina der" aria-label="Brillo">
    <svg viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="4"/>
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>
    </svg>
  </button>

  <div id="velo" class="velo"></div>

  <div id="panelReloj" class="panel izq">
    <div class="selector">
      <label class="caja">
        <span id="vh" class="num">0</span>
        <span class="unidad">Horas</span>
        <select id="selH" aria-label="Horas"></select>
      </label>
      <span class="dos-puntos">:</span>
      <label class="caja">
        <span id="vm" class="num">30</span>
        <span class="unidad">Minutos</span>
        <select id="selM" aria-label="Minutos"></select>
      </label>
    </div>
    <div class="atajos">
      <button class="chip" data-min="15">15 min</button>
      <button class="chip" data-min="30">30 min</button>
      <button class="chip" data-min="60">1 h</button>
      <button class="chip" data-min="120">2 h</button>
    </div>
    <button id="programar" class="programar">Programar apagado</button>
    <div id="avisoReloj" class="aviso"></div>
  </div>

  <div id="panelBrillo" class="panel der">
    <div class="fila">
      <input id="brillo" type="range" min="0" max="100" step="1" value="50" aria-label="Brillo">
      <span id="pct" class="pct">50</span>
    </div>
    <div id="avisoBrillo" class="aviso"></div>
  </div>

  <header>
    <div class="etiqueta"><span class="punto"></span>Red local</div>
    <h1>MANDO</h1>
  </header>

  <button id="apagar" class="encendido" onclick="accion('apagar')" aria-label="Apagar">
    <span class="anillo">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round">
        <path d="M12 3v8"/>
        <path d="M6.3 6.6a8 8 0 1 0 11.4 0"/>
      </svg>
    </span>
  </button>

  <section class="volumen">
    <div class="mando">
      <button class="redondo" data-vol="bajar" aria-label="Bajar volumen">
        <svg viewBox="0 0 24 24"><path d="M6 12h12"/></svg>
      </button>
      <button class="redondo pequeno" data-vol="silencio" aria-label="Silenciar">
        <svg viewBox="0 0 24 24">
          <path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/>
          <path d="M16 9.5l5 5M21 9.5l-5 5"/>
        </svg>
      </button>
      <button class="redondo" data-vol="subir" aria-label="Subir volumen">
        <svg viewBox="0 0 24 24"><path d="M6 12h12M12 6v12"/></svg>
      </button>
    </div>
  </section>

  <div class="acciones">
    <button class="btn" onclick="accion('reiniciar')">Reiniciar</button>
    <button class="btn" onclick="accion('cancelar')">Cancelar</button>
  </div>

  <div id="estado" class="estado"></div>
  <div id="nota" class="nota"></div>

<script>
  // En iOS, :active solo se activa si hay algún manejador de toque
  document.addEventListener('touchstart', () => {}, {passive: true});

  const $ = id => document.getElementById(id);
  const token = new URLSearchParams(location.search).get('t') || '';
  const estado = $('estado'), nota = $('nota');
  const botonApagar = $('apagar'), botonReloj = $('reloj');

  function enviar(nombre, extra = {}) {
    return fetch('/accion', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign({token, accion: nombre}, extra))
    });
  }

  // ---------- Mensajes breves (desaparecen solos, no pisan la cuenta atrás)
  let temporNota = null;
  function avisar(texto) {
    clearTimeout(temporNota);
    nota.textContent = texto || '';
    if (texto) temporNota = setTimeout(() => { nota.textContent = ''; }, 3500);
  }

  // ---------- Cuenta atrás (apagar, reiniciar o temporizador)
  const TEXTOS = {apagar: 'Apagando en', reiniciar: 'Reiniciando en', temporizador: 'Se apagará en'};
  let tic = null, fin = 0, pendiente = null;

  function formato(s) {
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
    const dos = n => String(n).padStart(2, '0');
    if (h) return h + ' h ' + dos(m) + ' min ' + dos(x) + ' s';
    if (m) return m + ' min ' + dos(x) + ' s';
    return x + ' s';
  }

  function parar() {
    clearInterval(tic); tic = null; pendiente = null;
    botonApagar.classList.remove('activo');
    botonReloj.classList.remove('activo');
    estado.textContent = '';
  }

  function cuentaAtras(tipo, segundos) {
    parar();
    pendiente = tipo;
    fin = Date.now() + segundos * 1000;
    (tipo === 'temporizador' ? botonReloj : botonApagar).classList.add('activo');
    const pintar = () => {
      const s = Math.max(0, Math.round((fin - Date.now()) / 1000));
      if (s <= 0) { parar(); estado.textContent = 'Hasta luego'; return; }
      estado.innerHTML = TEXTOS[tipo] + ' <b>' + formato(s) + '</b>';
    };
    pintar();
    tic = setInterval(pintar, 250);
  }

  async function accion(nombre) {
    try {
      const r = await enviar(nombre);
      const d = await r.json();
      if (!r.ok) { avisar(d.mensaje); return; }
      if (nombre === 'cancelar') { parar(); avisar(d.mensaje); return; }
      cuentaAtras(nombre, d.restante);
    } catch (e) {
      avisar('Sin conexión con el PC');
    }
  }

  // Al abrir la página (o volver a ella) se recupera lo que esté programado en el PC
  async function sincronizar() {
    try {
      const r = await enviar('estado');
      const d = await r.json();
      if (d.restante > 0) {
        const desfase = Math.abs((fin - Date.now()) / 1000 - d.restante);
        if (pendiente !== d.tipo || desfase > 2) cuentaAtras(d.tipo, d.restante);
      } else if (pendiente) {
        parar();
      }
    } catch (e) { /* sin conexión: se reintenta al volver a la página */ }
  }
  sincronizar();
  document.addEventListener('visibilitychange', () => { if (!document.hidden) sincronizar(); });

  // ---------- Paneles: solo uno abierto a la vez; el velo bloquea el resto
  const velo = $('velo');
  const paneles = {
    reloj:  {boton: botonReloj, panel: $('panelReloj'), alAbrir: abrirReloj},
    brillo: {boton: $('sol'),   panel: $('panelBrillo'), alAbrir: abrirBrillo},
  };
  let abierto = null;

  function abrirPanel(nombre) {
    cerrarPanel();
    const p = paneles[nombre];
    abierto = nombre;
    p.panel.classList.add('visible');
    p.boton.classList.add('abierto');
    velo.classList.add('visible');
    p.alAbrir();
  }

  function cerrarPanel() {
    if (!abierto) return;
    const p = paneles[abierto];
    p.panel.classList.remove('visible');
    p.boton.classList.remove('abierto');
    velo.classList.remove('visible');
    abierto = null;
  }

  Object.keys(paneles).forEach(nombre => {
    paneles[nombre].boton.addEventListener('click', () => {
      abierto === nombre ? cerrarPanel() : abrirPanel(nombre);
    });
  });
  velo.addEventListener('click', cerrarPanel);

  // ---------- Temporizador
  const selH = $('selH'), selM = $('selM'), vh = $('vh'), vm = $('vm');
  const avisoReloj = $('avisoReloj'), programar = $('programar');

  for (let h = 0; h <= 23; h++) selH.add(new Option(h + (h === 1 ? ' hora' : ' horas'), h));
  for (let m = 0; m <= 59; m++) selM.add(new Option(m + ' min', m));

  function pintarTiempo() {
    vh.textContent = selH.value;
    vm.textContent = String(selM.value).padStart(2, '0');
  }
  function fijarTiempo(minutos) {
    selH.value = Math.floor(minutos / 60);
    selM.value = minutos % 60;
    pintarTiempo();
    avisoReloj.textContent = '';
  }
  selH.addEventListener('change', pintarTiempo);
  selM.addEventListener('change', pintarTiempo);
  document.querySelectorAll('.chip').forEach(c =>
    c.addEventListener('click', () => fijarTiempo(parseInt(c.dataset.min, 10))));

  // Recuerda el último tiempo usado en este móvil
  let ultimo = 30;
  try { ultimo = parseInt(localStorage.getItem('mando-minutos'), 10) || 30; } catch (e) {}
  fijarTiempo(ultimo);

  function abrirReloj() {
    if (pendiente) {
      programar.disabled = true;
      avisoReloj.textContent = 'Ya hay un apagado en marcha. Pulsa Cancelar si quieres cambiarlo.';
    } else {
      programar.disabled = false;
      avisoReloj.textContent = '';
    }
  }

  programar.addEventListener('click', async () => {
    const minutos = parseInt(selH.value, 10) * 60 + parseInt(selM.value, 10);
    if (minutos < 1) { avisoReloj.textContent = 'Elige al menos 1 minuto'; return; }
    programar.disabled = true;
    try {
      const r = await enviar('temporizador', {segundos: minutos * 60});
      const d = await r.json();
      if (!r.ok) { avisoReloj.textContent = d.mensaje; programar.disabled = false; return; }
      try { localStorage.setItem('mando-minutos', String(minutos)); } catch (e) {}
      cerrarPanel();
      cuentaAtras('temporizador', d.restante);
    } catch (e) {
      avisoReloj.textContent = 'Sin conexión con el PC';
      programar.disabled = false;
    }
  });

  // ---------- Volumen: un toque = un paso; mantener pulsado = repetición continua
  function volumen(nombre) {
    enviar(nombre).catch(() => avisar('Sin conexión con el PC'));
  }

  document.querySelectorAll('[data-vol]').forEach(b => {
    let espera = null, repeticion = null;
    const fin = () => { clearTimeout(espera); clearInterval(repeticion); espera = repeticion = null; };
    b.addEventListener('pointerdown', () => {
      const nombre = b.dataset.vol;
      volumen(nombre);
      if (nombre !== 'silencio') {
        espera = setTimeout(() => { repeticion = setInterval(() => volumen(nombre), 140); }, 400);
      }
    });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach(ev => b.addEventListener(ev, fin));
    b.addEventListener('contextmenu', e => e.preventDefault());
  });

  // ---------- Brillo
  const barra = $('brillo'), pct = $('pct'), avisoBrillo = $('avisoBrillo');

  function pintarBrillo(v) {
    barra.value = v;
    barra.style.setProperty('--p', v + '%');
    pct.textContent = v;
  }
  pintarBrillo(50);

  async function abrirBrillo() {
    avisoBrillo.textContent = '';
    try {
      const r = await enviar('leer_brillo');
      const d = await r.json();
      if (d.brillo === null || d.brillo === undefined) {
        barra.disabled = true;
        avisoBrillo.textContent = 'El monitor no responde por DDC/CI';
      } else {
        barra.disabled = false;
        pintarBrillo(d.brillo);
      }
    } catch (e) {
      avisoBrillo.textContent = 'Sin conexión con el PC';
    }
  }

  // Mientras arrastras se envía como mucho cada 200 ms (DDC/CI es lento), y siempre el valor final
  let ultimoEnvio = 0, diferido = null;
  function mandarBrillo(v) {
    ultimoEnvio = Date.now();
    enviar('brillo', {valor: v}).catch(() => { avisoBrillo.textContent = 'Sin conexión con el PC'; });
  }
  barra.addEventListener('input', () => {
    const v = parseInt(barra.value, 10);
    pintarBrillo(v);
    clearTimeout(diferido);
    if (Date.now() - ultimoEnvio > 200) mandarBrillo(v);
    else diferido = setTimeout(() => mandarBrillo(v), 200);
  });
</script>
</body>
</html>"""


class Manejador(BaseHTTPRequestHandler):
    def _responder(self, codigo, cuerpo, tipo="application/json"):
        datos = cuerpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def _json(self, codigo, mensaje, **extra):
        self._responder(codigo, json.dumps({"mensaje": mensaje, **extra}, ensure_ascii=False))

    def do_GET(self):
        url = urlparse(self.path)
        # El icono no es secreto: Safari lo pide sin token al añadir a la pantalla de inicio
        if url.path in ("/icono.png", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png", "/favicon.ico"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(ICONO_PNG)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(ICONO_PNG)
            return
        if url.path != "/":
            return self._responder(404, "No encontrado", "text/plain")
        token = parse_qs(url.query).get("t", [""])[0]
        if not hmac.compare_digest(token, TOKEN):
            return self._responder(403, "Acceso denegado", "text/plain")
        self._responder(200, PAGINA.replace("__VERSION_ICONO__", VERSION_ICONO), "text/html")

    def do_POST(self):
        if self.path != "/accion":
            return self._json(404, "Ruta desconocida")
        try:
            longitud = min(int(self.headers.get("Content-Length", 0)), 1024)
            datos = json.loads(self.rfile.read(longitud) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, "Petición mal formada")

        if not hmac.compare_digest(str(datos.get("token", "")), TOKEN):
            return self._json(403, "Token incorrecto")

        nombre = datos.get("accion")

        if nombre in TECLAS_VOLUMEN:
            pulsar_tecla(TECLAS_VOLUMEN[nombre])
            return self._json(200, "")

        if nombre == "leer_brillo":
            return self._json(200, "", brillo=leer_brillo())

        if nombre == "brillo":
            try:
                valor = max(0, min(100, int(datos.get("valor"))))
            except (TypeError, ValueError):
                return self._json(400, "Valor de brillo no válido")
            ok = fijar_brillo(valor)
            return self._json(200 if ok else 500, "" if ok else "El monitor no responde por DDC/CI")

        if nombre == "estado":
            actual = consultar_programado()
            if actual is None:
                return self._json(200, "", tipo=None, restante=0)
            return self._json(200, "", tipo=actual[0], restante=actual[1])

        if nombre == "cancelar":
            habia = desprogramar()
            # Por si hubiera un apagado programado desde fuera con "shutdown /t"
            externo = ejecutar(["shutdown", "/a"])
            return self._json(200, "" if (habia or externo) else "No había nada pendiente")

        if nombre in ("apagar", "reiniciar", "temporizador"):
            if nombre == "temporizador":
                try:
                    segundos = int(datos.get("segundos"))
                except (TypeError, ValueError):
                    return self._json(400, "Tiempo no válido")
                if not TEMPORIZADOR_MIN <= segundos <= TEMPORIZADOR_MAX:
                    return self._json(400, "Elige entre 1 minuto y 23 h 59 min")
            else:
                segundos = SEGUNDOS_AVISO

            if not programar(nombre, segundos):
                return self._json(409, "Ya hay un apagado en marcha. Pulsa Cancelar primero")
            return self._json(200, "", tipo=nombre, restante=segundos)

        return self._json(400, "Acción no válida")

    def log_message(self, formato, *args):
        pass  # silencio: con pythonw no hay consola


if __name__ == "__main__":
    print(f"Abre esto en el iPhone (misma wifi):\n  http://{ip_local()}:{PUERTO}/?t={TOKEN}\n")
    threading.Thread(target=vigilante, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PUERTO), Manejador).serve_forever()
