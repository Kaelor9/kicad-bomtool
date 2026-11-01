import argparse
import os
import sys
import threading
import webbrowser

from . import __version__, updater
from .server import make_server, serve

TITLE = "KiCad BOM-tjek"


class WindowApi:
    """Called from the page as window.pywebview.api.* when running in the app window."""

    def open_url(self, url):
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            webbrowser.open(url)


def run_window(port):
    """Open the program in its own window (Edge WebView2). Returns False if that isn't possible."""
    try:
        import webview  # noqa: PLC0415 - optional, the browser is the fallback
    except ImportError:
        return False
    server, url = make_server(port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    try:
        webview.create_window(f"{TITLE} {__version__}", url, width=1400, height=900, min_size=(900, 600),
                              js_api=WindowApi(), text_select=True)
        webview.start(private_mode=False, storage_path=os.path.join(updater.app_dir(), "webview"))
    except Exception as e:  # noqa: BLE001 - e.g. no WebView2 runtime: fall back to the browser
        print(f"Kunne ikke åbne programvinduet ({e}) – bruger browseren i stedet.")
        server.shutdown()
        return False
    server.shutdown()
    return True


def main():
    ap = argparse.ArgumentParser(description="KiCad BOM- og footprint-værktøj")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)))
    ap.add_argument("--browser", action="store_true", help="Brug browseren i stedet for programvinduet")
    ap.add_argument("--no-browser", action="store_true", help="Kun server – åbn hverken vindue eller browser")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args()
    if sys.stdout is None:            # the .exe has no console window
        sys.stdout = sys.stderr = open(os.devnull, "w")
    updater.cleanup()
    if args.no_browser:
        serve(args.port, False)
    elif args.browser or not run_window(args.port):
        serve(args.port, True)


if __name__ == "__main__":
    main()
