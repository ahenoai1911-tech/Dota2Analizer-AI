"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-17

Полная начальная схема: users, missions, user_missions, shop_items,
user_inventory, transactions, bot_user_prefs, bot_tracked_players.

Включает bootstrap дефолтных миссий и товаров магазина.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id BIGINT PRIMARY KEY,
        steam_id BIGINT,
        username TEXT,
        coins INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        premium_until TIMESTAMP,
        ai_requests_used INTEGER DEFAULT 0,
        ai_requests_reset_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS missions (
        id SERIAL PRIMARY KEY,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        requirement TEXT NOT NULL,
        target_value INTEGER NOT NULL,
        reward_coins INTEGER NOT NULL,
        reward_xp INTEGER NOT NULL,
        icon TEXT DEFAULT '🎯'
    );

    CREATE TABLE IF NOT EXISTS user_missions (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL REFERENCES users(telegram_id),
        mission_id INTEGER NOT NULL REFERENCES missions(id),
        progress INTEGER DEFAULT 0,
        completed BOOLEAN DEFAULT FALSE,
        claimed BOOLEAN DEFAULT FALSE,
        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS user_missions_tgid_idx
        ON user_missions(telegram_id);
    CREATE INDEX IF NOT EXISTS user_missions_assigned_idx
        ON user_missions(telegram_id, assigned_at);

    CREATE TABLE IF NOT EXISTS shop_items (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        type TEXT NOT NULL,
        price INTEGER NOT NULL,
        icon TEXT DEFAULT '🎁',
        data TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS shop_items_name_unique
        ON shop_items(name);

    CREATE TABLE IF NOT EXISTS user_inventory (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL REFERENCES users(telegram_id),
        item_id INTEGER NOT NULL REFERENCES shop_items(id),
        quantity INTEGER DEFAULT 1,
        acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL REFERENCES users(telegram_id),
        type TEXT NOT NULL,
        amount INTEGER NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS bot_user_prefs (
        telegram_id BIGINT PRIMARY KEY,
        notifications BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS bot_tracked_players (
        telegram_id BIGINT NOT NULL,
        player_id TEXT NOT NULL,
        last_winrate REAL,
        last_kda REAL,
        added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TIMESTAMP,
        PRIMARY KEY (telegram_id, player_id)
    );
    CREATE INDEX IF NOT EXISTS bot_tracked_players_tgid_idx
        ON bot_tracked_players(telegram_id);
    """)

    # Seed default missions
    op.execute("""
    INSERT INTO missions (type, title, description, requirement, target_value, reward_coins, reward_xp, icon)
    SELECT * FROM (VALUES
        ('daily','Победная серия','Выиграй 3 матча подряд','win_streak',3,100,150,'🔥'),
        ('daily','Мастер фарма','Набери 600+ GPM в матче','gpm',600,75,120,'💰'),
        ('daily','Высокий KDA','Сыграй матч с KDA 4+','kda',4,80,130,'⭐'),
        ('daily','Командный игрок','Сделай 15+ ассистов в матче','assists',15,60,100,'🤝'),
        ('daily','Победитель','Выиграй 1 матч','wins',1,30,60,'🏅'),
        ('weekly','Марафонец','Сыграй 20 матчей','matches',20,300,500,'🏃'),
        ('weekly','Доминатор','Выиграй 10 игр','wins',10,400,600,'👑'),
        ('weekly','Стабильность','Держи WR выше 50% (последние 20)','winrate',50,250,400,'📈'),
        ('weekly','Боец','Набери средний KDA 3+ (последние 20)','avg_kda',3,200,350,'⚔️'),
        ('monthly','Легенда','Выиграй 50 игр','wins',50,1000,2000,'🏆'),
        ('monthly','Несокрушимый','Достигни винрейта 55%+','winrate',55,1200,2500,'💎'),
        ('monthly','Профессионал','Набери средний KDA 4.0+','avg_kda',4,900,1800,'🎯')
    ) AS v(type,title,description,requirement,target_value,reward_coins,reward_xp,icon)
    WHERE NOT EXISTS (SELECT 1 FROM missions);
    """)

    # Seed default shop items (убран `Premium 30 дней` — продаётся только за Stars)
    op.execute("""
    INSERT INTO shop_items (name, description, type, price, icon, data)
    VALUES
        ('XP Booster x2','Удваивает получаемый опыт на 24 часа','booster_xp',500,'⚡','duration:24,multiplier:2'),
        ('Coin Booster x2','Удваивает награды монет на 24 часа','booster_coins',600,'💰','duration:24,multiplier:2'),
        ('Mega Booster','x2 XP и монеты на 48 часов','booster_mega',1500,'🚀','duration:48,xp:2,coins:2'),
        ('Золотая рамка','Золотая рамка для профиля','cosmetic_frame',300,'🖼️','color:gold'),
        ('Алмазная рамка','Алмазная рамка для профиля','cosmetic_frame',800,'💎','color:diamond'),
        ('Титул: Ветеран','Отображается в профиле','cosmetic_title',500,'🎖️','title:Ветеран'),
        ('Титул: Легенда','Отображается в профиле','cosmetic_title',1000,'👑','title:Легенда'),
        ('AI Запросы +10','10 дополнительных AI запросов','special_ai',250,'🤖','queries:10'),
        ('Сброс миссий','Обновляет все текущие миссии','special_refresh',300,'🔄','refresh:all')
    ON CONFLICT (name) DO NOTHING;

    -- Убираем старый premium-товар из магазина (он продаётся только за Stars)
    DELETE FROM shop_items WHERE type = 'premium';
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS bot_tracked_players;
        DROP TABLE IF EXISTS bot_user_prefs;
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS user_inventory;
        DROP TABLE IF EXISTS user_missions;
        DROP TABLE IF EXISTS shop_items;
        DROP TABLE IF EXISTS missions;
        DROP TABLE IF EXISTS users;
    """)
