"""referrals + demo flags

Revision ID: 0002_referrals_demo
Revises: 0001_initial
Create Date: 2026-04-17

Добавляет:
  - users.demo_deep_used      BOOLEAN — использовал ли юзер бесплатный deep-анализ
  - users.referred_by         BIGINT  — кто пригласил (одноразово, NULL если сам пришёл)
  - users.ref_premium_granted BOOLEAN — получил ли он 7д Premium за 3 приглашённых
  - table referrals(ref_code TEXT PRIMARY KEY, owner_telegram_id BIGINT, created_at)
  - users.ref_code TEXT UNIQUE — личный код приглашения (для простоты — /ref_<id>)
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_referrals_demo"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS demo_deep_used       BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS referred_by          BIGINT,
        ADD COLUMN IF NOT EXISTS ref_premium_granted  BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS ref_code             TEXT;

    CREATE UNIQUE INDEX IF NOT EXISTS users_ref_code_unique ON users(ref_code);
    CREATE INDEX IF NOT EXISTS users_referred_by_idx ON users(referred_by);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS users_referred_by_idx;
        DROP INDEX IF EXISTS users_ref_code_unique;
        ALTER TABLE users
            DROP COLUMN IF EXISTS ref_code,
            DROP COLUMN IF EXISTS ref_premium_granted,
            DROP COLUMN IF EXISTS referred_by,
            DROP COLUMN IF EXISTS demo_deep_used;
    """)
