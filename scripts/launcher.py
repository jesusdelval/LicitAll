#!/usr/bin/env python3
"""LicitAll — Lanzador visual con comprobación automática de actualizaciones en GitHub."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.actualizar import (  # noqa: E402
    check_for_updates,
    download_and_deploy_update,
    get_local_version_info,
)

SERVER_HOST = os.environ.get("LICITALL_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("LICITALL_PORT", "8000"))
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/"
HEALTH_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/api/health"
WIN_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _get_python_gui_executable() -> str:
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pyw = exe[:-10] + "pythonw.exe"
        if os.path.exists(pyw):
            return pyw
    return exe


def _is_server_alive() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


class SplashLauncher:
    """Minimal corporate splash window styled like ProfitAll."""

    def __init__(self) -> None:
        import tkinter as tk

        self.tk = tk
        self.root = tk.Tk()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        self.version = get_local_version_info().get("version", "1.0.0")
        self.root.title("LicitAll")
        self.root.overrideredirect(True)
        self.root.configure(bg="#cbd5e1")
        self.root.attributes("-topmost", True)

        w, h = 500, 260
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        card = tk.Frame(self.root, bg="#ffffff", bd=1, relief="solid")
        card.pack(fill="both", expand=True)

        top_bar = tk.Frame(card, bg="#e20074", height=5)
        top_bar.pack(fill="x", side="top")

        body = tk.Frame(card, bg="#ffffff")
        body.pack(fill="both", expand=True, padx=26, pady=22)

        tk.Label(
            body,
            text="LICITALL",
            font=("Segoe UI", 16, "bold"),
            fg="#e20074",
            bg="#ffffff",
        ).pack(anchor="w")

        tk.Label(
            body,
            text=f"Portal de Descubrimiento de Licitaciones · v{self.version}",
            font=("Segoe UI", 10),
            fg="#64748b",
            bg="#ffffff",
        ).pack(anchor="w", pady=(2, 18))

        self.status_var = tk.StringVar(value="Iniciando...")
        tk.Label(
            body,
            textvariable=self.status_var,
            font=("Segoe UI", 11, "bold"),
            fg="#0f172a",
            bg="#ffffff",
        ).pack(anchor="w")

        self.detail_var = tk.StringVar(value="Comprobando actualizaciones en GitHub...")
        tk.Label(
            body,
            textvariable=self.detail_var,
            font=("Segoe UI", 9),
            fg="#64748b",
            bg="#ffffff",
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def set_status(self, title: str, detail: str = "") -> None:
        self.root.after(0, lambda: (self.status_var.set(title), self.detail_var.set(detail)))

    def close(self) -> None:
        self.root.after(0, self.root.destroy)

    def run(self) -> None:
        threading.Thread(target=self._workflow, daemon=True).start()
        self.root.mainloop()

    def _workflow(self) -> None:
        try:
            # 1. Comprobar y desplegar actualizaciones desde GitHub
            self.set_status("Comprobando actualizaciones...", "Conectando con GitHub...")
            check = check_for_updates()
            if check.get("ok") and check.get("has_update"):
                self.set_status(
                    "Descargando actualización...",
                    f"Nueva versión detectada ({check['remote_sha'][:7]}). Desplegando...",
                )
                res = download_and_deploy_update(
                    remote_sha=check["remote_sha"],
                    repo=check["repo"],
                    branch=check["branch"],
                    token=check.get("token", ""),
                )
                if res.get("ok"):
                    self.set_status(
                        "Aplicación actualizada",
                        f"Desplegados {res.get('updated_files', 0)} archivos correctamente.",
                    )
                    time.sleep(0.9)
                else:
                    self.set_status("Aviso de actualización", res.get("error", "Continuando con versión local"))
                    time.sleep(1.2)
            elif check.get("ok"):
                self.set_status("Aplicación al día", "No hay cambios nuevos en GitHub.")
                time.sleep(0.4)
            else:
                self.set_status("Iniciando sin conexión a GitHub", check.get("error", ""))
                time.sleep(0.6)

            # 2. Arrancar servidor local si no está ya corriendo
            if not _is_server_alive():
                self.set_status("Iniciando servidor local...", f"Arrancando en {SERVER_URL}")
                env = os.environ.copy()
                env["LICITALL_NO_BROWSER"] = "1"
                log_fh = open(BASE_DIR / "sync_update.log", "a", encoding="utf-8")
                subprocess.Popen(
                    [_get_python_gui_executable(), str(BASE_DIR / "run.py")],
                    cwd=str(BASE_DIR),
                    env=env,
                    stdout=log_fh,
                    stderr=log_fh,
                    creationflags=WIN_NO_WINDOW,
                )
                for _ in range(40):
                    if _is_server_alive():
                        break
                    time.sleep(0.25)

            # 3. Abrir en el navegador predeterminado y cerrar splash
            webbrowser.open(SERVER_URL)
            time.sleep(0.3)
        except Exception as exc:
            self.set_status("Error al iniciar LicitAll", str(exc))
            time.sleep(3.5)
        finally:
            self.close()


if __name__ == "__main__":
    SplashLauncher().run()
