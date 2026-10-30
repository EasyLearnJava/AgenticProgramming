"""
main.py: the app's entry point. Vercel looks in this file for a top-level `app`, and so does Uvicorn on your computer:
`uv run uvicorn main:app --reload --no-access-log`, then open http://127.0.0.1:8000. (The app writes its own line per
request, without the query string; Uvicorn's access log would write another, with it.)
"""

from nimbus.app import create_app

app = create_app()
