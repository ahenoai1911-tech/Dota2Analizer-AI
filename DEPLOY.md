# 🚀 Деплой на Railway

Полный пошаговый гайд. Время: **~15 минут**.

---

## Шаг 0 — Что тебе понадобится

| Что | Откуда |
|---|---|
| **Бот в Telegram** | [@BotFather](https://t.me/BotFather) → `/newbot` → сохрани `BOT_TOKEN` |
| **Имя бота** | Оттуда же (без `@`) — нужно для реферальных ссылок |
| **Railway аккаунт** | [railway.app](https://railway.app) — бесплатно до 500ч/мес |
| **GitHub репозиторий** | Чтобы Railway подтягивал код |
| **Groq API key** | [console.groq.com](https://console.groq.com) — бесплатный для AI (llama-3.3-70b) |
| **Stratz API token** *(опционально)* | [stratz.com/api](https://stratz.com/api) — для более быстрых данных |

---

## Шаг 1 — Залить код в GitHub

```bash
cd C:\CLode
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/TUSER/dota2-analyzer.git
git push -u origin main
```

⚠️ **НЕ коммить `.env`!** Он в `.gitignore`.

---

## Шаг 2 — Создать проект на Railway

1. Зайди на [railway.app/new](https://railway.app/new) → **Deploy from GitHub repo** → выбери свой репо.
2. Railway автоматически увидит `nixpacks.toml` и `requirements.txt` — билдит Python-проект.
3. После первого билда проект **упадёт** — это ожидаемо, нет БД и переменных.

---

## Шаг 3 — Добавить PostgreSQL

В твоём проекте на Railway:

1. **+ New** → **Database** → **Add PostgreSQL**.
2. Railway создаст сервис `Postgres` и сам выдаст `DATABASE_URL`.
3. Открой свой сервис (не БД, а веб-сервис) → **Variables** → **Add Reference** → выбери `Postgres.DATABASE_URL`.

Теперь `DATABASE_URL` автоматически прокинут.

---

## Шаг 4 — Environment Variables

В сервисе → **Variables** → **Raw Editor** → вставь:

```env
BOT_TOKEN=1234567890:ABC...
BOT_USERNAME=your_bot_name_without_at
BOT_MODE=webhook
WEBAPP_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
ALLOWED_ORIGINS=https://${{RAILWAY_PUBLIC_DOMAIN}}

TELEGRAM_WEBHOOK_SECRET=СЛУЧАЙНАЯ_СТРОКА_32_СИМВОЛА
GROQ_API_KEY=gsk_...
STRATZ_TOKEN=

PREMIUM_STARS_PRICE=129
PREMIUM_DAYS=30
REF_BONUS_COUNT=3
REF_BONUS_DAYS=7

INIT_DATA_MAX_AGE=86400
AUTH_DEV_BYPASS=0
```

### Как сгенерить `TELEGRAM_WEBHOOK_SECRET`:
```powershell
# PowerShell
[System.Web.Security.Membership]::GeneratePassword(32, 0)
# или
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### `${{RAILWAY_PUBLIC_DOMAIN}}`
Это шаблон Railway — подставится автоматом (например `dota2-analyzer-production.up.railway.app`).

---

## Шаг 5 — Сгенерировать публичный домен

Сервис → **Settings** → **Networking** → **Generate Domain**.

Получишь что-то типа: `dota2-analyzer-production.up.railway.app`

---

## Шаг 6 — Деплой

Railway автоматически ре-деплоит при изменении переменных. Дождись статуса **Success** (1-2 минуты).

Проверь логи — должно быть:
```
INFO:alembic.runtime.migration:Running upgrade  -> 0001_initial
INFO:alembic.runtime.migration:Running upgrade 0001_initial -> 0002_referrals_demo
INFO:     Uvicorn running on http://0.0.0.0:$PORT
```

Открой в браузере: `https://your-domain.up.railway.app/` → должно быть `{"status":"ok","message":"Dota 2 Analyzer API v2.4"}`.

---

## Шаг 7 — Привязать Telegram Webhook

Замени `<BOT_TOKEN>`, `<DOMAIN>`, `<SECRET>` и выполни:

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" ^
  -d "url=https://<DOMAIN>/webhook" ^
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>" ^
  -d "allowed_updates=[\"message\",\"pre_checkout_query\",\"callback_query\",\"inline_query\"]"
```

**PowerShell:**
```powershell
$token  = "твой_BOT_TOKEN"
$domain = "dota2-analyzer-production.up.railway.app"
$secret = "твой_TELEGRAM_WEBHOOK_SECRET"

Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$token/setWebhook" -Body @{
    url = "https://$domain/webhook"
    secret_token = $secret
    allowed_updates = '["message","pre_checkout_query","callback_query","inline_query"]'
}
```

Проверь что привязалось:
```
https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```
Должно быть `"url": "https://.../webhook"` и `"pending_update_count": 0`.

---

## Шаг 8 — Привязать Web App к боту

У [@BotFather](https://t.me/BotFather):
1. `/mybots` → выбери бота → **Bot Settings** → **Menu Button** → **Configure Menu Button**.
2. Введи URL: `https://<DOMAIN>/` (тот же домен Railway — там же `index.html` раздаётся через FastAPI? **НЕТ**, сейчас `index.html` не раздаётся FastAPI — он лежит отдельно).

### ⚠️ Важно про `index.html`

У тебя сейчас `index.html` **не раздаётся** через FastAPI. Два варианта:

**Вариант A (проще)** — раздавать через FastAPI:

Добавь в `main.py` перед `if __name__`:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

@app.get("/app")
async def webapp_index():
    return FileResponse("index.html")
```

И выстави `WEBAPP_URL=https://<DOMAIN>/app`.

**Вариант B (правильнее)** — хостить `index.html` отдельно:
- [Cloudflare Pages](https://pages.cloudflare.com) или [Netlify](https://netlify.com) — бесплатно.
- Залей `index.html` → получишь отдельный домен → выставь `WEBAPP_URL=https://webapp.pages.dev`.

---

## Шаг 9 — Проверка

1. Открой бота в Telegram → `/start`.
2. Должно написать приветствие + кнопка **🎮 Открыть анализатор**.
3. Нажми кнопку → открывается Web App → сверху справа должен быть badge `🆓 Free`.
4. Попробуй `/player Miracle-` → должна прийти карточка.
5. `/premium` → должен прийти инвойс на 129⭐ (если у тебя есть Stars баланс — можно заплатить для теста).
6. `/invite` → должна прийти ссылка-приглашение.
7. `/deep` → должен работать demo-анализ (первый раз бесплатно).

---

## 🐛 Траблшутинг

### Логи не покажут ничего полезного?
```
railway logs           # CLI
```
или в Web UI: сервис → **Deployments** → последний → **View Logs**.

### Миграции не применились?
Запусти вручную:
```bash
railway run alembic upgrade head
```

### `DATABASE_URL not set`?
Забыл добавить Reference на Postgres. Шаг 3.

### Webhook возвращает 403?
- `TELEGRAM_WEBHOOK_SECRET` в `setWebhook` не совпадает с env.
- Либо `BOT_MODE` != `webhook`.

### Web App не открывается / показывает `Authentication required`?
- `index.html` открыт не через Telegram (локально в браузере) → auth не работает.
- Для локального теста выстави `AUTH_DEV_BYPASS=1`. **В проде — 0.**

### `401 Invalid Telegram initData`?
Web App открыт через старую ссылку, или `BOT_TOKEN` в env не совпадает с реальным. Пересоздай Web App и проверь токен.

### Покупка Premium выдаёт ошибку?
- `BOT_TOKEN` неверный → `createInvoiceLink` фейлится.
- Бот не одобрен для Stars → пиши [@BotSupport](https://t.me/BotSupport) или включай payments в BotFather.

---

## 📊 Мониторинг

- Railway показывает метрики (CPU, RAM, трафик) в сервисе → **Metrics**.
- Бесплатный план: $5 кредита/мес → хватает на маленький бот 24/7.
- Если выйдешь за лимит — Railway автоматически остановит сервис до следующего месяца.

---

## 🔄 Обновления

Любой `git push` в `main` → Railway автоматически ре-деплоит.

Если добавляешь новые миграции — `alembic upgrade head` запустится сам перед стартом (через `nixpacks.toml` / `Procfile`).

---

## ✅ Чек-лист перед релизом

- [ ] `.env` в `.gitignore`, не закоммичен
- [ ] `AUTH_DEV_BYPASS=0` в Railway env
- [ ] `PREMIUM_DEV_KEY` пустой (или отсутствует)
- [ ] `ALLOWED_ORIGINS` = реальный домен Web App, не `*`
- [ ] `TELEGRAM_WEBHOOK_SECRET` установлен и прокинут в `setWebhook`
- [ ] Webhook `getWebhookInfo` показывает правильный URL и `pending_update_count: 0`
- [ ] `/player` возвращает данные
- [ ] Web App badge показывает `🆓 Free`
- [ ] `/invite` создаёт корректный `https://t.me/{BOT_USERNAME}?start=r...` линк
- [ ] В логах нет `ERROR` (только `INFO`/`WARNING`)
