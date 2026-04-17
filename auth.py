"""
Telegram WebApp authentication.

Validates `initData` (HMAC-SHA256 with key = HMAC-SHA256("WebAppData", BOT_TOKEN))
as described in https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Usage:
    from fastapi import Depends
    from auth import require_tg_user, TgUser

    @app.post("/secure-endpoint")
    async def handler(user: TgUser = Depends(require_tg_user)):
        ...  # user.id guaranteed verified
"""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Request

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Позволяет отключить проверку в dev-режиме (НЕ использовать в проде)
AUTH_DEV_BYPASS = os.getenv("AUTH_DEV_BYPASS", "0") == "1"
# initData не должен быть старше этого (секунд). По умолчанию 24 часа.
INIT_DATA_MAX_AGE = int(os.getenv("INIT_DATA_MAX_AGE", str(24 * 3600)))


@dataclass
class TgUser:
    id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    is_premium: bool = False  # Telegram-premium (не наш), для сегментации
    language_code: str = ""


def _verify_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """
    Проверяет init_data (querystring из Telegram.WebApp.initData).
    Возвращает словарь распарсенных полей если подпись валидна, иначе None.
    """
    if not init_data or not bot_token:
        return None

    try:
        # parse_qsl сохраняет все поля (включая hash)
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None

    provided_hash = parsed.pop("hash", None)
    if not provided_hash:
        return None

    # data_check_string: все пары key=value, отсортированы по ключу, через \n
    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed.keys()))

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, provided_hash):
        return None

    # Проверка свежести
    auth_date = parsed.get("auth_date")
    if auth_date:
        try:
            if time.time() - int(auth_date) > INIT_DATA_MAX_AGE:
                return None
        except ValueError:
            return None

    return parsed


def _parse_user(fields: dict) -> Optional[TgUser]:
    user_raw = fields.get("user")
    if not user_raw:
        return None
    try:
        u = json.loads(user_raw)
    except Exception:
        return None
    uid = u.get("id")
    if not uid:
        return None
    return TgUser(
        id=int(uid),
        username=u.get("username", "") or "",
        first_name=u.get("first_name", "") or "",
        last_name=u.get("last_name", "") or "",
        is_premium=bool(u.get("is_premium", False)),
        language_code=u.get("language_code", "") or "",
    )


async def require_tg_user(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(default=None),
) -> TgUser:
    """
    FastAPI dependency. Верифицирует пользователя через initData.

    Порядок получения initData:
      1. Header `X-Telegram-Init-Data` (предпочтительный способ для POST).
      2. Query param `tg_init_data` (для GET-запросов).

    В dev-режиме (AUTH_DEV_BYPASS=1) принимает `?telegram_id=...` или поле
    в JSON-теле и доверяет ему — НИКОГДА не использовать в проде.
    """
    init_data = x_telegram_init_data or request.query_params.get("tg_init_data")

    if init_data:
        fields = _verify_init_data(init_data, BOT_TOKEN)
        if not fields:
            raise HTTPException(status_code=401, detail="Invalid Telegram initData")
        user = _parse_user(fields)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid user payload")
        return user

    # DEV fallback
    if AUTH_DEV_BYPASS:
        tid = request.query_params.get("telegram_id")
        if not tid:
            # попробуем тело
            try:
                body = await request.json()
                tid = body.get("telegram_id")
            except Exception:
                tid = None
        if tid:
            return TgUser(id=int(tid))

    raise HTTPException(status_code=401, detail="Authentication required (provide X-Telegram-Init-Data)")


async def optional_tg_user(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(default=None),
) -> Optional[TgUser]:
    """Мягкая версия: возвращает None если initData отсутствует/некорректен."""
    try:
        return await require_tg_user(request, x_telegram_init_data)
    except HTTPException:
        return None
