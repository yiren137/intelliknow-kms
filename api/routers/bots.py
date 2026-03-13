"""Bot status endpoints."""
from fastapi import APIRouter, HTTPException
from api.schemas import BotStatus, BotUpdate
from db.database import get_db_connection

router = APIRouter(prefix="/api/v1/bots", tags=["bots"])


@router.get("", response_model=list[BotStatus])
def get_bots():
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, platform, is_active, last_seen_at, created_at FROM bot_integrations"
        ).fetchall()

    results = []
    for r in rows:
        bot = dict(r)
        # Dynamically compute is_active: bot is considered active only if it
        # sent a heartbeat within the last 2 minutes
        if bot["last_seen_at"]:
            with get_db_connection() as conn:
                stale = conn.execute(
                    "SELECT (strftime('%s','now') - strftime('%s', ?)) > 120 AS stale",
                    (bot["last_seen_at"],),
                ).fetchone()
            bot["is_active"] = not stale["stale"]
        else:
            bot["is_active"] = False
        results.append(BotStatus(**bot))

    return results


@router.put("/{platform}", response_model=BotStatus)
def update_bot(platform: str, body: BotUpdate):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM bot_integrations WHERE platform = ?", (platform,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Bot '{platform}' not found")

        if body.is_active is not None:
            if body.is_active:
                conn.execute(
                    "UPDATE bot_integrations SET is_active = ?, last_seen_at = datetime('now') WHERE platform = ?",
                    (int(body.is_active), platform),
                )
            else:
                conn.execute(
                    "UPDATE bot_integrations SET is_active = ? WHERE platform = ?",
                    (int(body.is_active), platform),
                )

        row = conn.execute(
            "SELECT id, platform, is_active, last_seen_at, created_at FROM bot_integrations WHERE platform = ?",
            (platform,),
        ).fetchone()

    return BotStatus(**dict(row))


def heartbeat(platform: str):
    """Called by bots to mark themselves as alive."""
    with get_db_connection() as conn:
        conn.execute(
            """UPDATE bot_integrations
               SET is_active = 1, last_seen_at = datetime('now')
               WHERE platform = ?""",
            (platform,),
        )
