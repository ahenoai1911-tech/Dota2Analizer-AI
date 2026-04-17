# Procfile для Railway / Heroku
# BOT_MODE=webhook → FastAPI принимает апдейты TG на /webhook (запускается web).
# BOT_MODE=polling → запусти worker (bot.py), а web по желанию как REST API.
# Миграции накатываются через alembic перед стартом.
web: alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT
worker: python bot.py
