"""Single-command launcher for the LicitAll portal."""

from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn


def _open_browser(url: str) -> None:
    """Open the portal in a normal tab of the user's default browser."""
    webbrowser.open(url)


if __name__ == "__main__":
    host = os.environ.get("LICITALL_HOST", "127.0.0.1")
    port = int(os.environ.get("LICITALL_PORT", "8000"))
    if os.environ.get("LICITALL_NO_BROWSER") != "1":
        threading.Timer(1.2, _open_browser, args=(f"http://{host}:{port}",)).start()
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
