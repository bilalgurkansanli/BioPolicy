"""Apply the numbered SQL migrations.

    python -m api.scripts.migrate            # apply everything pending
    python -m api.scripts.migrate --status   # show what would run, change nothing

Exists because the Supabase CLI is not a dependency of this project and adding
one more tool to the setup path is not worth it for something this small.

## Rules it enforces

**Forward-only, in numeric order.** `0002` never runs before `0010` because the
filenames sort as strings somewhere else in the toolchain.

**One transaction per migration.** Postgres DDL is transactional, so a migration
that fails partway leaves nothing behind — the next run retries it cleanly. The
exception is `create index concurrently`, which cannot run inside a transaction;
there is none in this project, and if one is added this runner needs to learn
about it (see docs/RUNBOOK.md).

**Applied migrations are recorded with a checksum.** Editing a file that has
already run is the classic way a schema drifts apart between environments, so
the runner refuses rather than silently ignoring the change.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import sys
from pathlib import Path

import asyncpg

from api.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
NUMBERED = re.compile(r"^(\d+)_")

BOOTSTRAP = """
create table if not exists schema_migrations (
    version     text primary key,
    filename    text not null,
    checksum    text not null,
    applied_at  timestamptz not null default now()
)
"""

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def discover() -> list[tuple[str, Path]]:
    found: list[tuple[int, str, Path]] = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = NUMBERED.match(path.name)
        if not match:
            raise ValueError(f"{path.name} does not start with a version number")
        found.append((int(match.group(1)), match.group(1), path))
    # Sorted numerically, not lexically: 0010 must follow 0009.
    return [(version, path) for _, version, path in sorted(found)]


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


async def run(*, status_only: bool) -> int:
    settings = get_settings()
    if not settings.database_url:
        print(f"{RED}DATABASE_URL is not set.{RESET}")
        return 2

    migrations = discover()
    print(f"{len(migrations)} migration files in {MIGRATIONS_DIR}\n")

    # WHY statement_cache_size=0: the connection string points at Supabase's
    # transaction pooler (port 6543), which is the right choice for a
    # scale-to-zero deployment — short-lived instances, many of them, none
    # holding a session open. The catch is that pgbouncer in transaction mode
    # hands a different backend connection to each statement, while asyncpg
    # caches server-side prepared statements by name and assumes they persist.
    # The two disagree intermittently, surfacing as
    # `prepared statement "__asyncpg_stmt_x__" does not exist` on a query that
    # worked a moment earlier. Disabling the cache makes asyncpg use unnamed
    # statements, which are per-round-trip and therefore pooler-safe.
    connection = await asyncpg.connect(settings.database_url, statement_cache_size=0)
    try:
        await connection.execute(BOOTSTRAP)
        applied = {
            row["version"]: row["checksum"]
            for row in await connection.fetch("select version, checksum from schema_migrations")
        }

        pending: list[tuple[str, Path]] = []
        for version, path in migrations:
            digest = checksum(path)
            if version not in applied:
                pending.append((version, path))
                print(f"  {YELLOW}PENDING{RESET}  {path.name}")
            elif applied[version] != digest:
                print(f"  {RED}CHANGED{RESET}  {path.name}")
                print(
                    f"           {DIM}This file was edited after it was applied. Migrations "
                    f"are forward-only —\n           write a new one that corrects it "
                    f"rather than editing this.{RESET}"
                )
                return 1
            else:
                print(f"  {GREEN}APPLIED{RESET}  {path.name}")

        if status_only:
            print(f"\n{len(pending)} pending. Nothing was changed.")
            return 0
        if not pending:
            print(f"\n{GREEN}Schema is up to date.{RESET}")
            return 0

        print()
        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            try:
                async with connection.transaction():
                    await connection.execute(sql)
                    await connection.execute(
                        "insert into schema_migrations (version, filename, checksum) "
                        "values ($1, $2, $3)",
                        version,
                        path.name,
                        checksum(path),
                    )
            except asyncpg.PostgresError as exc:
                print(f"  {RED}FAILED{RESET}   {path.name}")
                print(f"           {exc.__class__.__name__}: {exc}")
                print(
                    f"\n{DIM}Nothing from this migration was applied — Postgres DDL is\n"
                    f"transactional. Fix the cause and re-run; earlier migrations stay "
                    f"applied.{RESET}"
                )
                return 1
            print(f"  {GREEN}OK{RESET}       {path.name}")

        print(f"\n{GREEN}{len(pending)} migration(s) applied.{RESET}")
        return 0
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status", action="store_true", help="Report what would run; change nothing."
    )
    args = parser.parse_args()
    return asyncio.run(run(status_only=args.status))


if __name__ == "__main__":
    sys.exit(main())
