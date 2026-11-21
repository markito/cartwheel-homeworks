"""Staff ticket search and assignment, exercised without a model."""

import asyncio
import json
from pathlib import Path

import pytest
from agents.tool_context import ToolContext

from agent import db
from agent.agent import TOOLS_BY_ROLE, escalate_to_human_logic
from agent.auth import AuthContext
from agent.tools import find_my_tickets
from seed.ticket_assignments import add_ticket_assignments


@pytest.mark.parametrize("ctx", [AuthContext(1, "shopper"), AuthContext(9002, "merchant", 2)])
def test_ticket_search_is_staff_only(ctx: AuthContext) -> None:
    assert "find_my_tickets" not in [tool.name for tool in TOOLS_BY_ROLE[ctx.role]]
    assert find_my_tickets(ctx)["error"] == "permission_denied"


def test_search_assigned_tickets_through_registered_tool(world_copy: Path) -> None:
    shopper = AuthContext(1, "shopper")
    staff = AuthContext(9501, "support")
    created = [
        escalate_to_human_logic(shopper, "Shipping delay", "Tracking has stalled")["ticket_id"]
        for _ in range(30)
    ]
    # The dev world has five staff and 150 seeded tickets. New ticket 151 goes to 9501.
    assigned = created[::5]
    # A ticket opened by 9501 can be assigned to someone else.
    escalate_to_human_logic(staff, "Unrelated ticket", "")
    opened_by_staff = escalate_to_human_logic(staff, "Shipping delay", "")["ticket_id"]
    tool = next(t for t in TOOLS_BY_ROLE["support"] if t.name == "find_my_tickets")
    arguments = json.dumps({"query": " SHIPPING "})
    context = ToolContext(
        context=staff, tool_name=tool.name, tool_call_id="test", tool_arguments=arguments
    )
    result = asyncio.run(tool.on_invoke_tool(context, arguments))
    assert result["ok"]
    ids = [ticket["ticket_id"] for ticket in result["tickets"]]
    assert ids == assigned[::-1][:5]
    assert opened_by_staff not in ids
    assert find_my_tickets(staff)["tickets"][0]["summary"] == "Unrelated ticket"
    assert find_my_tickets(staff, "absent phrase") == {"ok": True, "tickets": []}


def test_existing_database_upgrade_preserves_tickets_and_assignments(world_copy: Path) -> None:
    with db.connection() as conn, conn:
        conn.execute("DROP INDEX idx_escalations_assignee")
        conn.execute("ALTER TABLE escalations DROP COLUMN assignee_id")
        original = conn.execute("SELECT * FROM escalations ORDER BY id").fetchall()
        add_ticket_assignments(conn)
        assert conn.execute(
            "SELECT id, user_id, store_id, order_id, summary, context, created_at "
            "FROM escalations ORDER BY id"
        ).fetchall() == original
        assert conn.execute(
            "SELECT count(*) FROM escalations JOIN users ON users.id = escalations.assignee_id "
            "WHERE users.role = 'support'"
        ).fetchone()[0] == len(original)
        conn.execute("UPDATE escalations SET assignee_id = 9505 WHERE id = 1")
        add_ticket_assignments(conn)
        assert conn.execute("SELECT assignee_id FROM escalations WHERE id = 1").fetchone()[0] == 9505
