"""`python -m narratix` starts the web app and opens it in your browser."""

import threading
import webbrowser

import uvicorn

HOST, PORT = "127.0.0.1", 8000  # localhost only: nothing is exposed to the network

if __name__ == "__main__":
    threading.Timer(1.2, webbrowser.open, args=[f"http://{HOST}:{PORT}"]).start()
    uvicorn.run("narratix.server:app", host=HOST, port=PORT)
