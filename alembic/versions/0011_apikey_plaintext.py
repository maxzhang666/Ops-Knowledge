"""ApiKey: replace key_hash with raw_key (plaintext storage for internal system)

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('api_keys', sa.Column('raw_key', sa.String(255), nullable=True))
    # Backfill: use key_prefix as placeholder for existing rows (original keys unrecoverable)
    op.execute("UPDATE api_keys SET raw_key = key_prefix || '...(migrated)' WHERE raw_key IS NULL")
    op.alter_column('api_keys', 'raw_key', nullable=False)
    op.create_unique_constraint('uq_api_keys_raw_key', 'api_keys', ['raw_key'])
    op.drop_constraint('api_keys_key_hash_key', 'api_keys', type_='unique')
    op.drop_column('api_keys', 'key_hash')


def downgrade() -> None:
    op.add_column('api_keys', sa.Column('key_hash', sa.String(255), nullable=True))
    op.execute("UPDATE api_keys SET key_hash = 'migrated_' || id WHERE key_hash IS NULL")
    op.alter_column('api_keys', 'key_hash', nullable=False)
    op.create_unique_constraint('api_keys_key_hash_key', 'api_keys', ['key_hash'])
    op.drop_constraint('uq_api_keys_raw_key', 'api_keys', type_='unique')
    op.drop_column('api_keys', 'raw_key')
