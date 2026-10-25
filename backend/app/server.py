"""Entry point for the desktop app's bundled backend.

The app starts this with --port 0 and reads one line from stdout:
    BRIEF_READY http://127.0.0.1:<port>
Everything else goes to the log file. --parent-pid makes us exit if the app dies
without cleaning up, so a crashed app never leaves an orphaned server behind.
"""

import argparse
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
from pathlib import Path


def _watch_parent(pid: int) -> None:
    while True:
        time.sleep(2)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            logging.getLogger(__name__).info("App process %s is gone; shutting down", pid)
            os._exit(0)
        except PermissionError:
            pass  # exists, just not ours to signal


def _setup_logging(log_dir: str | None) -> None:
    # With a log dir, stderr stays quiet so the app only sees crashes there.
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handlers = [
            logging.handlers.RotatingFileHandler(Path(log_dir) / "backend.log", maxBytes=2_000_000, backupCount=3)
        ]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="brief-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument("--data-dir")
    parser.add_argument("--static-dir", help="serve the web UI from here")
    parser.add_argument("--log-dir")
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args(argv)

    # config reads these at import time, so set them before importing the app.
    if args.data_dir:
        os.environ["BRIEF_DATA_DIR"] = args.data_dir
    if args.static_dir:
        os.environ["BRIEF_STATIC_DIR"] = args.static_dir
    _setup_logging(args.log_dir)

    import uvicorn

    from .main import app

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    port = sock.getsockname()[1]

    if args.parent_pid:
        threading.Thread(target=_watch_parent, args=(args.parent_pid,), daemon=True).start()

    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))

    def announce() -> None:
        while not server.started:
            if server.should_exit:
                return
            time.sleep(0.05)
        print(f"BRIEF_READY http://{args.host}:{port}", flush=True)

    threading.Thread(target=announce, daemon=True).start()
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
