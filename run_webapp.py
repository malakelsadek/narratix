"""
Convenience launcher for the EPUB -> Audiobook web app.
Starts the local server and opens it in your browser.
"""

import threading
import time
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = 8000


def open_browser():
    time.sleep(1.2)
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("webapp.server:app", host=HOST, port=PORT, reload=False)
