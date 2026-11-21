"""Staff routing for new tickets and for worlds created before assignments existed."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable


def assign_tickets(conn: sqlite3.Connection, ticket_ids: Iterable[int]) -> None:
    """Distribute unassigned tickets by ticket ID across the current support roster."""
    staff = [
        row[0] for row in conn.execute("SELECT id FROM users WHERE role = 'support' ORDER BY id")
    ]
    if staff:
        conn.executemany(
            "UPDATE escalations SET assignee_id = ? WHERE id = ? AND assignee_id IS NULL",
            ((staff[(ticket_id - 1) % len(staff)], ticket_id) for ticket_id in ticket_ids),
        )


def add_ticket_assignments(conn: sqlite3.Connection) -> None:
    """Upgrade the escalations table inside the caller's write transaction."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(escalations)")}
    if "assignee_id" in columns:
        return
    conn.execute("ALTER TABLE escalations ADD COLUMN assignee_id INTEGER REFERENCES users(id)")
    ticket_ids = [row[0] for row in conn.execute("SELECT id FROM escalations")]
    assign_tickets(conn, ticket_ids)
    conn.execute("CREATE INDEX idx_escalations_assignee ON escalations(assignee_id, created_at, id)")


if __name__ == "__main__":
    from agent.db import connection

    with connection() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        add_ticket_assignments(conn)
