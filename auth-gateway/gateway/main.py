"""ASGI-точка входа: uvicorn gateway.main:app --host 0.0.0.0 --port 8010"""

from .app import create_app

app = create_app()
