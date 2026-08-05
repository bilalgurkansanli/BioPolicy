"""Postgres connection pool.

One setting here is load-bearing and easy to lose in a refactor:
`statement_cache_size=0`.

We connect through Supabase's **transaction** pooler (port 6543), which is the
right shape for a scale-to-zero deployment — many short-lived instances, none
holding a session open. The cost is that pgbouncer in transaction mode hands a
different backend connection to each statement, while asyncpg caches
server-side prepared statements by name and assumes they persist across
statements on the same connection.

Those two assumptions are incompatible, and they fail *intermittently*: a query
that worked a second ago raises
`prepared statement "__asyncpg_stmt_3__" does not exist`. Disabling the cache
makes asyncpg use unnamed statements, which live for one round trip and are
therefore pooler-safe.

If someone later switches `DATABASE_URL` to the session pooler (port 5432) this
setting becomes unnecessary but stays harmless, so it is unconditional rather
than conditional on the port — a conditional would be one more thing to get
wrong.
"""

from __future__ import annotations

import asyncpg

from api.config import get_settings
from api.logging_config import get_logger

log = get_logger(__name__)

# Small on purpose. Each serverless instance holds its own pool, and the pooler
# has a global connection ceiling shared across every instance — a generous
# per-instance pool is how a scale-out event exhausts it.
MIN_POOL_SIZE = 1
MAX_POOL_SIZE = 5


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    settings = get_settings()
    resolved = dsn or settings.database_url
    if not resolved:
        raise RuntimeError("DATABASE_URL is not configured")

    pool = await asyncpg.create_pool(
        resolved,
        min_size=MIN_POOL_SIZE,
        max_size=MAX_POOL_SIZE,
        # See the module docstring. Do not remove.
        statement_cache_size=0,
        command_timeout=60,
    )
    if pool is None:  # pragma: no cover - asyncpg returns None only on misuse
        raise RuntimeError("failed to create a connection pool")

    log.info("db_pool_created", min_size=MIN_POOL_SIZE, max_size=MAX_POOL_SIZE)
    return pool
