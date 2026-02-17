"""PIDA System Tray — entry point.

Usage: python -m agent.tray
Main thread: pystray icon
Daemon thread: uvicorn FastAPI server
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)

_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.png"
_DASHBOARD_URL = "http://127.0.0.1:8765"


def _run_server() -> None:
    """Start uvicorn in the current thread (called from daemon thread)."""
    import uvicorn
    from agent.config import settings

    uvicorn.run(
        "agent.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


def _open_dashboard(_icon=None, _item=None) -> None:
    webbrowser.open(_DASHBOARD_URL)


def _quit(icon, _item=None) -> None:
    icon.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Start server in daemon thread
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()
    logger.info("Server thread started")

    try:
        import pystray
        from PIL import Image

        image = Image.open(_ICON_PATH)
        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", _open_dashboard, default=True),
            pystray.MenuItem("Quit", _quit),
        )
        icon = pystray.Icon("PIDA", image, "PIDA - Personal Intrusion Detection Agent", menu)
        logger.info("System tray icon starting")
        icon.run()
    except ImportError:
        logger.warning("pystray not available — running server only (Ctrl+C to stop)")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
    except Exception:
        logger.exception("Tray icon failed — running server only")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
