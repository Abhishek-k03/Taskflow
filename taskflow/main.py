# main.py - kept as a shim so `uvicorn main:app` still works from this directory

from taskflow.app import create_app

app = create_app()
