"""Phase 6: message insert NOTIFY trigger

Learn: PostgreSQL LISTEN/NOTIFY enables instant push notifications.
When a message is inserted, the trigger fires pg_notify with the
recipient and team info. The dispatcher process LISTENs on the
'new_message' channel and dispatches agent turns in <100ms.

Also adds triggers for human_request resolution and task status changes.

Revision ID: 85a67264382e
Revises: ba9513c684e2
Create Date: 2026-02-27 02:57:33.328900
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85a67264382e'
down_revision: Union[str, None] = 'ba9513c684e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── Message insert trigger ──────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_new_message()
        RETURNS TRIGGER AS $$
        BEGIN
            PERFORM pg_notify('new_message', json_build_object(
                'message_id', NEW.id,
                'recipient_id', NEW.recipient_id,
                'recipient_type', NEW.recipient_type,
                'team_id', NEW.team_id,
                'task_id', NEW.task_id
            )::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER message_insert_notify
            AFTER INSERT ON messages
            FOR EACH ROW
            EXECUTE FUNCTION notify_new_message();
    """)

    # ─── Human request resolved trigger ──────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_human_request_resolved()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.status = 'pending' AND NEW.status IN ('resolved', 'expired') THEN
                PERFORM pg_notify('human_request_resolved', json_build_object(
                    'request_id', NEW.id,
                    'agent_id', NEW.agent_id,
                    'team_id', NEW.team_id,
                    'status', NEW.status
                )::text);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER human_request_status_notify
            AFTER UPDATE ON human_requests
            FOR EACH ROW
            EXECUTE FUNCTION notify_human_request_resolved();
    """)

    # ─── Task status change trigger ──────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_task_status_changed()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.status IS DISTINCT FROM NEW.status THEN
                PERFORM pg_notify('task_status_changed', json_build_object(
                    'task_id', NEW.id,
                    'team_id', NEW.team_id,
                    'old_status', OLD.status,
                    'new_status', NEW.status
                )::text);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER task_status_change_notify
            AFTER UPDATE ON tasks
            FOR EACH ROW
            EXECUTE FUNCTION notify_task_status_changed();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_status_change_notify ON tasks;")
    op.execute("DROP FUNCTION IF EXISTS notify_task_status_changed;")
    op.execute("DROP TRIGGER IF EXISTS human_request_status_notify ON human_requests;")
    op.execute("DROP FUNCTION IF EXISTS notify_human_request_resolved;")
    op.execute("DROP TRIGGER IF EXISTS message_insert_notify ON messages;")
    op.execute("DROP FUNCTION IF EXISTS notify_new_message;")
