import asyncio
import logging
import os
import httpx
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    InlineQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

import db as botdb

load_dotenv()
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── НАСТРОЙКИ ────────────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
WEBAPP_URL  = os.getenv("WEBAPP_URL", "https://your-domain.com")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
# polling: классический polling-bot; webhook: API (main.py) обрабатывает апдейты.
BOT_MODE    = os.getenv("BOT_MODE", "polling").lower()
TRACK_CHECK_INTERVAL = int(os.getenv("TRACK_CHECK_INTERVAL_SEC", "1800"))  # 30 min
TRACK_WR_THRESHOLD   = float(os.getenv("TRACK_WR_THRESHOLD", "0.5"))


# ════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════

async def fetch_player(query: str) -> dict | None:
    """Запрос к нашему бэкенду."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{BACKEND_URL}/player",
                params={"query": query},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error(f"fetch_player error: {e}")
        return None


def rank_name(rank) -> str:
    """Принимает либо числовой rank_tier (12, 55, 80), либо готовую строку."""
    if rank is None:
        return "Uncalibrated"
    if isinstance(rank, str):
        return rank
    ranks = {
        10: "Herald", 20: "Guardian", 30: "Crusader",
        40: "Archon",  50: "Legend",   60: "Ancient",
        70: "Divine",  80: "Immortal",
    }
    try:
        tier = int(int(rank) / 10) * 10
    except (TypeError, ValueError):
        return "Unknown"
    return ranks.get(tier, "Unknown")


def rank_emoji(rank) -> str:
    if rank is None:
        return "❓"
    if isinstance(rank, str):
        # map first word to emoji
        name = rank.split()[0].lower() if rank else ""
        m = {"herald":"🪵","guardian":"🛡️","crusader":"⚒️","archon":"🗡️",
             "legend":"⚔️","ancient":"🏅","divine":"💎","immortal":"🌟"}
        return m.get(name, "❓")
    emojis = {
        10:"🪵", 20:"🛡️", 30:"⚒️", 40:"🗡️",
        50:"⚔️", 60:"🏅", 70:"💎", 80:"🌟",
    }
    try:
        tier = int(int(rank) / 10) * 10
    except (TypeError, ValueError):
        return "❓"
    return emojis.get(tier, "❓")


def wr_emoji(wr: float) -> str:
    try: wr = float(wr)
    except (TypeError, ValueError): return "⚪"
    if wr >= 55: return "🟢"
    if wr >= 50: return "🟡"
    return "🔴"


def kda_emoji(kda: float) -> str:
    try: kda = float(kda)
    except (TypeError, ValueError): return "⚪"
    if kda >= 4: return "🌟"
    if kda >= 2.5: return "👍"
    return "💀"


def format_player_card(data: dict) -> str:
    """Форматирует карточку игрока под актуальную схему API (main.py v2.3)."""
    p = data.get("profile", {}) or {}
    s = data.get("stats", {}) or {}
    t = data.get("trend", {}) or {}

    rank_raw = p.get("rank") or p.get("rank_tier")
    rank_e = rank_emoji(rank_raw)
    rank_n = rank_name(rank_raw)

    winrate = s.get("winrate", 0)
    wins    = s.get("wins", 0)
    losses  = s.get("losses", 0)
    total   = s.get("total_matches", wins + losses)

    last5_kda  = t.get("last5_avg_kda")
    last20_kda = t.get("last20_avg_kda")
    last5_wr   = t.get("last5_winrate")
    last5_gpm  = t.get("last5_avg_gpm")

    streak = t.get("streak", {}) or {}
    streak_line = ""
    if streak.get("count", 0) >= 2:
        emoji = "🔥" if streak.get("type") == "win" else "❄️"
        kind = "побед" if streak.get("type") == "win" else "поражений"
        streak_line = f"\n{emoji} Серия: <b>{streak['count']}</b> {kind} подряд"

    kda_str = f"{last5_kda}" if last5_kda is not None else "?"
    gpm_str = f"{last5_gpm}" if last5_gpm is not None else "?"

    anon = " 🔒" if p.get("is_anonymous") else ""
    mmr = f"  ·  MMR ~{p['mmr_estimate']}" if p.get("mmr_estimate") else ""

    return (
        f"⚔️ <b>{p.get('name','Unknown')}</b>{anon}\n"
        f"{rank_e} <b>{rank_n}</b>{mmr}  ·  ID: <code>{data.get('account_id','?')}</code>\n"
        f"{'─' * 28}\n"
        f"{wr_emoji(winrate)} WinRate: <b>{winrate}%</b>  "
        f"(<b>{wins}W</b> / {losses}L · {total} игр)\n"
        f"{kda_emoji(last5_kda or 0)} KDA (last 5): <b>{kda_str}</b>  ·  "
        f"📊 KDA (last 20): <b>{last20_kda if last20_kda is not None else '?'}</b>\n"
        f"📈 WR last 5: <b>{last5_wr if last5_wr is not None else '?'}%</b>  ·  "
        f"💰 GPM last 5: <b>{gpm_str}</b>"
        f"{streak_line}\n"
        f"{'─' * 28}"
    )


def main_keyboard(player_id: int | None = None) -> InlineKeyboardMarkup:
    """Главная клавиатура."""
    buttons = [
        [InlineKeyboardButton("🚀 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
        [
            InlineKeyboardButton("🔍 Найти игрока", callback_data="cmd_search"),
            InlineKeyboardButton("📊 Топ героев", callback_data="cmd_heroes"),
        ],
        [
            InlineKeyboardButton("ℹ️ Помощь", callback_data="cmd_help"),
            InlineKeyboardButton("⚙️ Настройки", callback_data="cmd_settings"),
        ],
    ]
    if player_id:
        buttons.insert(1, [
            InlineKeyboardButton("🔔 Отслеживать", callback_data=f"track_{player_id}"),
            InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{player_id}"),
        ])
    return InlineKeyboardMarkup(buttons)


def player_keyboard(player_id: int, name: str) -> InlineKeyboardMarkup:
    """Клавиатура под карточкой игрока."""
    safe_name = name[:20]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔔 Отслеживать", callback_data=f"track_{player_id}"),
            InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{player_id}"),
        ],
        [
            InlineKeyboardButton("🚀 Открыть в приложении", web_app=WebAppInfo(
                url=f"{WEBAPP_URL}?player={player_id}"
            )),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="cmd_start")],
    ])


# ════════════════════════════════════════════════════════════════════════
#  КОМАНДЫ
# ════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/start"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        f"⚔️ <b>Dota 2 Analyzer</b> — анализирую статистику игроков\n\n"
        f"<b>Что умею:</b>\n"
        f"• 📊 Показывать WinRate, KDA, GPM/XPM\n"
        f"• 🏆 Топ героев по играм\n"
        f"• 💡 Давать советы по улучшению игры\n"
        f"• 🔔 Отслеживать игроков\n"
        f"• 🔍 Работать в инлайн-режиме\n\n"
        f"Используй кнопки ниже или команды:\n"
        f"/player <code>ник</code> — найти игрока\n"
        f"/track — отслеживаемые игроки\n"
        f"/help — помощь",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/help"""
    text = (
        "📖 <b>Все команды:</b>\n\n"
        "/start — главное меню\n"
        "/player <code>ник</code> — статистика игрока\n"
        "/player <code>steamID</code> — по Steam ID\n"
        "/track — список отслеживаемых\n"
        "/untrack <code>steamID</code> — перестать следить\n"
        "/top — мировой топ игроков\n"
        "/help — это сообщение\n\n"
        "🔍 <b>Инлайн-режим:</b>\n"
        "В любом чате напиши <code>@твой_бот ник_игрока</code>\n"
        "и получи карточку игрока прямо в чат!\n\n"
        "🌐 <b>Web App:</b>\n"
        "Полный интерфейс с графиками и таблицами — кнопка 🚀"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data="cmd_start")
    ]])
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def cmd_player(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/player <query>"""
    if not ctx.args:
        await update.message.reply_text(
            "❓ Укажи ник или Steam ID:\n<code>/player Miracle-</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    query = " ".join(ctx.args)
    msg = await update.message.reply_text(f"⏳ Ищу <b>{query}</b>...", parse_mode=ParseMode.HTML)

    data = await fetch_player(query)
    if not data:
        await msg.edit_text("❌ Игрок не найден. Проверь ник или попробуй Steam ID.")
        return

    card = format_player_card(data)
    pid  = data.get("account_id") or (data.get("profile") or {}).get("account_id")
    name = (data.get("profile") or {}).get("name", "")

    try:
        pid_int = int(pid) if pid is not None else 0
    except (TypeError, ValueError):
        pid_int = 0

    await msg.edit_text(
        card,
        parse_mode=ParseMode.HTML,
        reply_markup=player_keyboard(pid_int, name),
    )


async def cmd_track_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/track — список отслеживаемых игроков"""
    uid   = update.effective_user.id
    tracked = botdb.list_tracked(uid)

    if not tracked:
        await update.message.reply_text(
            "📋 У тебя нет отслеживаемых игроков.\n\n"
            "Найди игрока командой /player и нажми 🔔 Отслеживать",
        )
        return

    lines = ["🔔 <b>Отслеживаемые игроки:</b>\n"]
    for pid in tracked:
        lines.append(f"• <code>{pid}</code> — /player {pid}")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить всех", callback_data="track_refresh_all"),
        InlineKeyboardButton("🗑 Очистить", callback_data="track_clear"),
    ]])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def cmd_untrack(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/untrack <player_id>"""
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text("Укажи Steam ID: <code>/untrack 105248644</code>", parse_mode=ParseMode.HTML)
        return

    pid = ctx.args[0]
    if botdb.remove_tracked(uid, pid):
        await update.message.reply_text(f"✅ Игрок <code>{pid}</code> удалён из отслеживания.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"❓ Игрок <code>{pid}</code> не найден в списке.", parse_mode=ParseMode.HTML)


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/top — мировой топ"""
    msg = await update.message.reply_text("⏳ Загружаю мировой топ...")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.opendota.com/api/players/top")
            r.raise_for_status()
            players = r.json()[:10]

        lines = ["🌍 <b>Топ-10 игроков мира (OpenDota):</b>\n"]
        for i, p in enumerate(players, 1):
            name = p.get("personaname", "Unknown")
            pid  = p.get("account_id", "")
            lines.append(f"{i}. <b>{name}</b> — <code>/player {pid}</code>")

        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text("❌ Не удалось загрузить топ. Попробуй позже.")
        logger.error(f"cmd_top error: {e}")


# ════════════════════════════════════════════════════════════════════════
#  CALLBACK BUTTONS
# ════════════════════════════════════════════════════════════════════════

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    uid  = update.effective_user.id

    # ── /start ──
    if data == "cmd_start":
        user = update.effective_user
        await query.edit_message_text(
            f"👋 Привет, <b>{user.first_name}</b>!\n\n"
            f"⚔️ <b>Dota 2 Analyzer</b>\n\n"
            f"/player <code>ник</code> — найти игрока\n"
            f"/track — отслеживаемые\n"
            f"/help — помощь",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )

    # ── help ──
    elif data == "cmd_help":
        await cmd_help(update, ctx)

    # ── search hint ──
    elif data == "cmd_search":
        await query.edit_message_text(
            "🔍 <b>Поиск игрока:</b>\n\n"
            "Отправь команду:\n"
            "<code>/player Miracle-</code>\n"
            "<code>/player 105248644</code>\n\n"
            "или используй инлайн-режим:\n"
            "<code>@бот Dendi</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="cmd_start")
            ]]),
        )

    # ── heroes hint ──
    elif data == "cmd_heroes":
        await query.edit_message_text(
            "🏆 <b>Топ героев игрока:</b>\n\n"
            "Найди игрока и открой вкладку <b>Герои</b> в приложении:\n\n"
            "<code>/player Miracle-</code>  →  🚀 Открыть приложение",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="cmd_start")
            ]]),
        )

    # ── settings ──
    elif data == "cmd_settings":
        notif_on = botdb.get_notifications_enabled(uid)
        n_tracked = botdb.tracked_count(uid)
        icon     = "🔔" if notif_on else "🔕"
        label    = "Выключить уведомления" if notif_on else "Включить уведомления"

        await query.edit_message_text(
            f"⚙️ <b>Настройки</b>\n\n"
            f"{icon} Уведомления: <b>{'Вкл' if notif_on else 'Выкл'}</b>\n"
            f"📋 Отслеживаемых игроков: <b>{n_tracked}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(label, callback_data="toggle_notif")],
                [InlineKeyboardButton("◀️ Назад", callback_data="cmd_start")],
            ]),
        )

    # ── toggle notifications ──
    elif data == "toggle_notif":
        current = botdb.get_notifications_enabled(uid)
        new_val = not current
        botdb.set_notifications_enabled(uid, new_val)
        icon  = "🔔" if new_val else "🔕"
        await query.answer(
            f"{icon} Уведомления {'включены' if new_val else 'выключены'}",
            show_alert=True,
        )
        notif_on = new_val
        n_tracked = botdb.tracked_count(uid)
        label    = "Выключить уведомления" if notif_on else "Включить уведомления"
        await query.edit_message_text(
            f"⚙️ <b>Настройки</b>\n\n"
            f"{icon} Уведомления: <b>{'Вкл' if notif_on else 'Выкл'}</b>\n"
            f"📋 Отслеживаемых игроков: <b>{n_tracked}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(label, callback_data="toggle_notif")],
                [InlineKeyboardButton("◀️ Назад", callback_data="cmd_start")],
            ]),
        )

    # ── refresh all tracked ──
    elif data == "track_refresh_all":
        tracked = botdb.list_tracked(uid)
        if not tracked:
            await query.answer("Список пуст", show_alert=True)
            return
        await query.answer("⏳ Обновляю всех...")
        results = []
        for pid in tracked[:5]:  # Максимум 5 чтобы не ждать долго
            d = await fetch_player(str(pid))
            if d:
                s = d.get("stats", {}) or {}
                p = d.get("profile", {}) or {}
                t = d.get("trend", {}) or {}
                wr = s.get("winrate", 0)
                kda = t.get("last5_avg_kda", "-")
                results.append(
                    f"• <b>{p.get('name','Unknown')}</b> — WR: {wr_emoji(wr)}{wr}%  KDA(5): {kda}"
                )
        if results:
            await query.edit_message_text(
                "🔔 <b>Обновлённая статистика:</b>\n\n" + "\n".join(results),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="cmd_start")
                ]]),
            )

    # ── clear tracking ──
    elif data == "track_clear":
        botdb.clear_tracked(uid)
        await query.answer("🗑 Список очищен", show_alert=True)
        await query.edit_message_text(
            "✅ Список отслеживания очищен.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="cmd_start")
            ]]),
        )

    # ── track player ── (должно быть ПОСЛЕ track_refresh_all/track_clear)
    elif data.startswith("track_"):
        pid = data.split("_", 1)[1]
        if botdb.add_tracked(uid, pid):
            await query.answer(f"✅ Игрок {pid} добавлен в отслеживание!", show_alert=True)
        else:
            await query.answer("ℹ️ Игрок уже в списке отслеживания", show_alert=True)

    # ── refresh player ──
    elif data.startswith("refresh_"):
        pid  = data.split("_", 1)[1]
        await query.answer("⏳ Обновляю...")
        new_data = await fetch_player(pid)
        if new_data:
            card = format_player_card(new_data)
            name = (new_data.get("profile") or {}).get("name", "")
            try:
                pid_int = int(pid)
            except ValueError:
                pid_int = new_data.get("account_id", 0) or 0
            await query.edit_message_text(
                card + "\n\n<i>🔄 Данные обновлены</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=player_keyboard(pid_int, name),
            )
        else:
            await query.answer("❌ Не удалось обновить данные", show_alert=True)


# ════════════════════════════════════════════════════════════════════════
#  INLINE MODE
# ════════════════════════════════════════════════════════════════════════

async def on_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Инлайн-режим: @бот Miracle-"""
    query = update.inline_query.query.strip()
    if not query or len(query) < 2:
        return

    data = await fetch_player(query)
    if not data:
        results = [
            InlineQueryResultArticle(
                id="not_found",
                title="❌ Игрок не найден",
                description=f"По запросу «{query}» ничего нет",
                input_message_content=InputTextMessageContent(
                    f"❌ Игрок «{query}» не найден в OpenDota"
                ),
            )
        ]
    else:
        card = format_player_card(data)
        p    = data.get("profile", {}) or {}
        s    = data.get("stats", {}) or {}
        t    = data.get("trend", {}) or {}
        account_id = data.get("account_id") or p.get("account_id") or "0"
        rank_raw = p.get("rank") or p.get("rank_tier")
        kda_desc = t.get("last5_avg_kda", "-")
        results = [
            InlineQueryResultArticle(
                id=str(account_id),
                title=f"⚔️ {p.get('name','Unknown')}",
                description=(
                    f"{rank_emoji(rank_raw)} {rank_name(rank_raw)} · "
                    f"WR: {s.get('winrate', 0)}% · KDA(5): {kda_desc}"
                ),
                input_message_content=InputTextMessageContent(
                    card, parse_mode=ParseMode.HTML
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🚀 Открыть полный анализ",
                        url=f"{WEBAPP_URL}?player={account_id}",
                    )
                ]]),
            )
        ]

    await update.inline_query.answer(results, cache_time=60)


# ════════════════════════════════════════════════════════════════════════
#  WEB APP DATA
# ════════════════════════════════════════════════════════════════════════

async def on_webapp_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Данные из Web App."""
    import json
    try:
        data = json.loads(update.message.web_app_data.data)
        player = data.get("player", "Unknown")
        wr     = data.get("wr", 0)
        kda    = data.get("kda", 0)

        await update.message.reply_text(
            f"📊 Ты посмотрел статистику игрока <b>{player}</b>\n"
            f"WR: {wr_emoji(wr)} {wr}%  ·  KDA: {kda_emoji(kda)} {kda}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
    except Exception as e:
        logger.error(f"webapp data error: {e}")


# ════════════════════════════════════════════════════════════════════════
#  ФОНОВАЯ ЗАДАЧА — проверка отслеживаемых игроков
# ════════════════════════════════════════════════════════════════════════

async def check_tracked(app: Application) -> None:
    """
    Каждые N минут проверяем отслеживаемых игроков.
    Если WR изменился на порог+ — уведомляем пользователя.
    """
    while True:
        await asyncio.sleep(TRACK_CHECK_INTERVAL)
        logger.info("Проверка отслеживаемых игроков...")

        try:
            users = botdb.iter_users_with_notifications()
        except Exception as e:
            logger.error(f"Failed to load tracked users: {e}")
            continue

        for uid in users:
            try:
                tracked = botdb.list_tracked(uid)
            except Exception as e:
                logger.error(f"Failed to list tracked for uid={uid}: {e}")
                continue

            for pid in tracked:
                try:
                    new = await fetch_player(str(pid))
                    if not new:
                        continue

                    prev = botdb.get_last_seen(uid, pid) or {}
                    new_wr = new.get("stats", {}).get("winrate")
                    old_wr = prev.get("last_winrate")
                    new_kda = (new.get("trend") or {}).get("last5_avg_kda")

                    botdb.update_last_seen(uid, pid, new_wr, new_kda)

                    if (
                        old_wr is not None
                        and new_wr is not None
                        and abs(float(new_wr) - float(old_wr)) >= TRACK_WR_THRESHOLD
                    ):
                        direction = "вырос 📈" if new_wr > old_wr else "упал 📉"
                        try:
                            await app.bot.send_message(
                                chat_id=uid,
                                text=(
                                    f"🔔 <b>{new.get('profile', {}).get('name', 'Unknown')}</b>\n"
                                    f"WinRate {direction}: {old_wr}% → <b>{new_wr}%</b>"
                                ),
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception as send_err:
                            # Пользователь заблокировал бота / чат недоступен - не падаем
                            logger.warning(f"send_message failed uid={uid}: {send_err}")
                except Exception as e:
                    logger.error(f"Track check error uid={uid} pid={pid}: {e}")


# ════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ════════════════════════════════════════════════════════════════════════

def main() -> None:
    if BOT_MODE == "webhook":
        logger.info(
            "BOT_MODE=webhook → polling-бот НЕ запускается. "
            "Апдейты обрабатывает FastAPI (main.py, эндпоинт /webhook)."
        )
        return

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env!")

    # Убедимся что таблицы бота существуют (идемпотентно)
    try:
        botdb.ensure_bot_schema()
    except Exception as e:
        logger.error(f"ensure_bot_schema failed: {e}")

    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("player",  cmd_player))
    app.add_handler(CommandHandler("track",   cmd_track_list))
    app.add_handler(CommandHandler("untrack", cmd_untrack))
    app.add_handler(CommandHandler("top",     cmd_top))

    # Кнопки
    app.add_handler(CallbackQueryHandler(on_callback))

    # Инлайн
    app.add_handler(InlineQueryHandler(on_inline))

    # Web App данные
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp_data))

    # Фоновая задача (проверка отслеживаемых)
    async def post_init(application: Application) -> None:
        asyncio.create_task(check_tracked(application))

    app.post_init = post_init

    logger.info("🤖 Бот запущен в polling-режиме!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
