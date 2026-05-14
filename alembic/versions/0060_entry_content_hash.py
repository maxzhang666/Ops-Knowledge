"""entry content_hash for skip-unchanged update

#5 fix — add knowledge_entries.content_hash (sha256 hex). Used by
plugin.update_unit to short-circuit when content didn't actually change,
avoiding wasted rechunk + reembed cycles.

Existing rows are backfilled via SQL sha256(content::bytea) so the
column is immediately useful; future rows fill it at create/update time.

Revision ID: 0060_entry_content_hash
Revises: 0059_tag_governance
"""
from __future__ import annotations

from alembic import op

revision = "0060_entry_content_hash"
down_revision = "0059_tag_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. column nullable to avoid blocking on backfill
    op.execute(
        "ALTER TABLE knowledge_entries "
        "ADD COLUMN content_hash VARCHAR(64)"
    )
    # 2. backfill existing rows (uses pgcrypto.digest if installed, else fallback)
    # Postgres ships sha256 via pgcrypto extension; if not available we fall
    # back to md5 + length signature (no security implication, just a marker).
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto') THEN
                UPDATE knowledge_entries
                SET content_hash = encode(digest(content, 'sha256'), 'hex')
                WHERE content_hash IS NULL;
            ELSE
                -- Fallback: md5 is built-in. Lower precision but unblocks the
                -- migration. App-level writes always use sha256.
                UPDATE knowledge_entries
                SET content_hash = md5(content)
                WHERE content_hash IS NULL;
            END IF;
        END
        $$;
    """)
    # 3. index for future cross-KB dedup (Plan 31 redundancy scan)
    op.execute(
        "CREATE INDEX ix_knowledge_entries_content_hash "
        "ON knowledge_entries (content_hash)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_entries_content_hash")
    op.execute("ALTER TABLE knowledge_entries DROP COLUMN IF EXISTS content_hash")
