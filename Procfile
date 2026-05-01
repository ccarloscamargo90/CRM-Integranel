release: alembic upgrade head && python scripts/seed_admin.py
web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT --workers 2
