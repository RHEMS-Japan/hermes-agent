"""unblock(resolve=True) clears the same-cause loop-breaker state.

The loop-breaker (BLOCK_RECURRENCE_LIMIT) protects against unblockers that
retry the SAME situation. An unblocker acting strictly on new information
(a question answered by a human) opts out with resolve=True; a bare unblock
keeps the counter, preserving the original protection.
"""

import hermes_cli.kanban_db as kb


def _task_row(conn, task_id):
    return conn.execute(
        "SELECT status, block_kind, block_recurrences FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()


def _mk_running_task(conn):
    return kb.create_task(conn, title="q", initial_status="running")


def test_bare_unblock_keeps_recurrence_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))
    with kb.connect_closing() as conn:
        tid = _mk_running_task(conn)
        assert kb.block_task(conn, tid, reason="round 1", kind="needs_input")
        assert kb.unblock_task(conn, tid)
        row = _task_row(conn, tid)
        assert row["block_kind"] == "needs_input"
        assert row["block_recurrences"] == 1


def test_resolve_unblock_clears_recurrence_state_and_survives_two_rounds(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))
    with kb.connect_closing() as conn:
        tid = _mk_running_task(conn)

        # Round 1: question -> block -> answer -> resolve-unblock.
        assert kb.block_task(conn, tid, reason="round 1", kind="needs_input")
        assert kb.unblock_task(conn, tid, resolve=True)
        row = _task_row(conn, tid)
        assert row["block_kind"] is None
        assert row["block_recurrences"] == 0

        # Round 2: the same protocol-legal flow must NOT route to triage.
        conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (tid,))
        conn.commit()
        assert kb.block_task(conn, tid, reason="round 2", kind="needs_input")
        row = _task_row(conn, tid)
        assert row["status"] == "blocked", "second round was routed to triage"
        assert kb.unblock_task(conn, tid, resolve=True)
        assert _task_row(conn, tid)["block_recurrences"] == 0
