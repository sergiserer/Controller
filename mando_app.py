"""
mando_app.py — App de escritorio para MANDO.

Arranca el servidor de apagar_pc.py y muestra una ventanita con la dirección
(y un código QR) para abrir en el móvil. Al cerrar la ventana, se detiene.

Pensado para empaquetarlo como Mando.exe con PyInstaller (ver construir.ps1),
para que alguien sin conocimientos solo tenga que hacer doble clic.

    python mando_app.py        (para probarlo sin empaquetar)
"""

import base64
import os
import socket
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox

import apagar_pc  # reutiliza TODO el servidor: apagar, temporizador, volumen, brillo, icono

# Colores, a juego con la web
FONDO = "#1c1f24"
TEXTO = "#c9ced6"
TENUE = "#6b7380"
AZUL = "#4a78c2"
CAJA = "#14171c"
ACENTO = "#294a74"   # azul del botón principal, como el de la web

NOMBRE_INICIO = "Remote.lnk"   # acceso directo en la carpeta de Inicio de Windows

# Icono del acceso "Detener" (mando con X roja), incrustado para no depender de archivos sueltos.
ICONO_DETENER_ICO = base64.b64decode(
    "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"
)


def url_mando() -> str:
    return f"http://{apagar_pc.ip_local()}:{apagar_pc.PUERTO}/?t={apagar_pc.TOKEN}"


def puerto_libre() -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", apagar_pc.PUERTO))
        return True
    except OSError:
        return False
    finally:
        s.close()


def arrancar_servidor():
    """Lanza el servidor y el vigilante del temporizador en segundo plano."""
    servidor = apagar_pc.ThreadingHTTPServer(("0.0.0.0", apagar_pc.PUERTO), apagar_pc.Manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    threading.Thread(target=apagar_pc.vigilante, daemon=True).start()
    return servidor


# ---------------------------------------------------------------- Arranque con Windows
def ruta_inicio() -> str:
    return os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup", NOMBRE_INICIO)


def arranca_con_windows() -> bool:
    return os.path.exists(ruta_inicio())


def fijar_arranque(activar: bool):
    destino = ruta_inicio()
    if activar:
        exe = sys.executable          # la propia Mando.exe cuando está empaquetado
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
            "$s.TargetPath='%s';"
            "$s.WorkingDirectory='%s';"
            "$s.Description='MANDO: control del PC desde el movil';"
            "$s.Save()"
        ) % (destino, exe, os.path.dirname(exe))
        subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif os.path.exists(destino):
        try:
            os.remove(destino)
        except OSError:
            pass


# ---------------------------------------------------------------- Accesos directos del escritorio
def _escritorio() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _crear_lnk(ruta, destino, argumentos, descripcion, icono):
    # En una cadena PowerShell entre comillas simples, una comilla simple se escapa duplicándola.
    esc = lambda t: t.replace("'", "''")
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        "$s.TargetPath='%s';$s.Arguments='%s';"
        "$s.WorkingDirectory='%s';$s.Description='%s';"
        "$s.IconLocation='%s';$s.Save()"
    ) % (esc(ruta), esc(destino), esc(argumentos),
         esc(os.path.dirname(destino) or "."), esc(descripcion), esc(icono))
    subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def crear_accesos_escritorio():
    """La primera vez, crea en el escritorio 'Mando - Iniciar' y 'Mando - Detener'."""
    escritorio = _escritorio()
    iniciar = os.path.join(escritorio, "Remote - Start.lnk")
    detener = os.path.join(escritorio, "Remote - Stop.lnk")
    if os.path.exists(iniciar):
        return   # ya se crearon antes

    exe = sys.executable
    # Iniciar: abre esta misma app. Usa el icono del propio .exe.
    _crear_lnk(iniciar, exe, "", "Open Remote", exe + ",0")

    # Detener: cierra el proceso Mando. Escribe su icono (mando con X) junto al .exe.
    ico = os.path.join(apagar_pc.CARPETA_BASE, "mando_detener.ico")
    try:
        with open(ico, "wb") as f:
            f.write(ICONO_DETENER_ICO)
    except OSError:
        ico = exe + ",0"
    nombre_proc = os.path.splitext(os.path.basename(exe))[0]
    cmd = "Stop-Process -Name '%s' -Force -ErrorAction SilentlyContinue" % nombre_proc
    _crear_lnk(detener, "powershell.exe",
               "-NoProfile -WindowStyle Hidden -Command \"" + cmd + "\"",
               "Stop Remote", ico)


# ---------------------------------------------------------------- Código QR (opcional)
def dibujar_qr(canvas, texto, lado_px):
    """Dibuja el QR en el canvas. Devuelve True si se pudo (requiere la librería qrcode)."""
    try:
        import qrcode
    except ImportError:
        return False
    qr = qrcode.QRCode(border=3, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(texto)
    qr.make(fit=True)
    matriz = qr.get_matrix()
    n = len(matriz)
    paso = lado_px / n
    canvas.config(width=lado_px, height=lado_px)
    canvas.delete("all")
    canvas.create_rectangle(0, 0, lado_px, lado_px, fill="#ffffff", outline="#ffffff")
    for y, fila in enumerate(matriz):
        for x, negro in enumerate(fila):
            if negro:
                canvas.create_rectangle(x * paso, y * paso, (x + 1) * paso, (y + 1) * paso,
                                        fill="#000000", outline="#000000")
    return True


# ---------------------------------------------------------------- Ventana
def main():
    if not puerto_libre():
        root = tk.Tk(); root.withdraw()
        messagebox.showinfo("Remote",
                            "Remote is already running.\n\n"
                            "If you don't see it, check the taskbar, or close the "
                            "other Remote window before opening this one.")
        return

    arrancar_servidor()
    try:
        crear_accesos_escritorio()
    except Exception:
        pass
    url = url_mando()

    root = tk.Tk()
    root.title("Remote")
    root.configure(bg=FONDO)
    root.resizable(False, False)

    # Icono de la ventana (el mando en pixel art, ya incrustado en apagar_pc)
    icono = None
    try:
        icono = tk.PhotoImage(data=base64.b64encode(apagar_pc.ICONO_PNG).decode())
        root.iconphoto(True, icono)
        root._icono = icono  # evita que el recolector lo borre
    except Exception:
        pass

    marco = tk.Frame(root, bg=FONDO)
    marco.pack(padx=34, pady=28)

    # El mando en pixel art, arriba del todo
    if icono is not None:
        try:
            mini = icono.subsample(3)
            lbl_icono = tk.Label(marco, image=mini, bg=FONDO)
            lbl_icono.image = mini
            lbl_icono.pack(pady=(0, 8))
        except Exception:
            pass

    tk.Label(marco, text="REMOTE", bg=FONDO, fg=TEXTO,
             font=("Segoe UI Light", 24)).pack()
    tk.Label(marco, text="OPEN THIS IN YOUR PHONE'S BROWSER",
             bg=FONDO, fg=TENUE, font=("Segoe UI", 8)).pack(pady=(12, 10))

    # La dirección, seleccionable
    caja = tk.Entry(marco, justify="center", bd=0, relief="flat",
                    bg=CAJA, fg=AZUL, font=("Consolas", 11), readonlybackground=CAJA)
    caja.insert(0, url)
    caja.config(state="readonly")
    caja.pack(fill="x", ipady=9)

    def copiar():
        root.clipboard_clear()
        root.clipboard_append(url)
        boton_copiar.config(text="COPIED")
        root.after(1500, lambda: boton_copiar.config(text="COPY ADDRESS"))

    boton_copiar = tk.Button(marco, text="COPY ADDRESS", command=copiar,
                             bg=ACENTO, fg="#eef3fb", activebackground=AZUL,
                             activeforeground="#ffffff", bd=0, relief="flat",
                             font=("Segoe UI", 9, "bold"), cursor="hand2")
    boton_copiar.pack(fill="x", pady=(10, 0), ipady=9)

    # Código QR (si la librería qrcode está disponible)
    qr_canvas = tk.Canvas(marco, bg=FONDO, highlightthickness=0, bd=0)
    if dibujar_qr(qr_canvas, url, 190):
        tk.Label(marco, text="OR SCAN WITH YOUR PHONE CAMERA",
                 bg=FONDO, fg=TENUE, font=("Segoe UI", 8)).pack(pady=(18, 10))
        qr_canvas.pack()

    # Arrancar con Windows
    var_inicio = tk.BooleanVar(value=arranca_con_windows())

    def alternar_inicio():
        fijar_arranque(var_inicio.get())

    tk.Checkbutton(marco, text="Start with Windows", variable=var_inicio,
                   command=alternar_inicio, bg=FONDO, fg=TENUE,
                   selectcolor=CAJA, activebackground=FONDO, activeforeground=TEXTO,
                   bd=0, highlightthickness=0, font=("Segoe UI", 9)).pack(pady=(18, 2))

    tk.Label(marco, text="Keep this window open while you use the remote.\n"
                         "To stop it, close the window.",
             bg=FONDO, fg=TENUE, font=("Segoe UI", 8), justify="center").pack(pady=(10, 0))

    root.update_idletasks()
    an, al = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - an) // 2
    y = (root.winfo_screenheight() - al) // 3
    root.geometry(f"+{x}+{y}")
    root.mainloop()


if __name__ == "__main__":
    main()
