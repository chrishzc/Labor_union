"""Typed owner for LINE user state and onboarding-task lifecycle."""

from __future__ import annotations


_ROLES = frozenset({"customer", "staff", "union_staff"})


def activate_follow(cursor, line_user_id: str) -> None:
    """Activate a follow event without deciding its presentation tasks."""
    cursor.execute(
        """INSERT INTO line_users (line_user_id,status,followed_at,last_event_at,onboarding_started_at)
           VALUES (%s,'active',NOW(),NOW(),NOW())
           ON DUPLICATE KEY UPDATE status='active',followed_at=NOW(),
               blocked_at=NULL,last_event_at=NOW()""",
        (line_user_id,),
    )


def block_unfollow(cursor, line_user_id: str) -> None:
    """Block a user and cancel only undelivered onboarding messages."""
    cursor.execute(
        """UPDATE line_users SET status='blocked',blocked_at=NOW(),last_event_at=NOW()
           WHERE line_user_id=%s""",
        (line_user_id,),
    )
    cancel_pending_onboarding(cursor, line_user_id)


def cancel_pending_onboarding(cursor, line_user_id: str) -> None:
    cursor.execute(
        """UPDATE line_tasks SET status='cancelled'
           WHERE to_user_id=%s AND status='pending'
             AND idempotency_key LIKE 'onboarding:%%'""",
        (line_user_id,),
    )


def assign_role(cursor, line_user_id: str, role: str) -> None:
    if role not in _ROLES:
        raise ValueError("unsupported_line_user_role")
    cursor.execute(
        """INSERT INTO line_users (line_user_id,role,status,last_event_at)
           VALUES (%s,%s,'active',NOW())
           ON DUPLICATE KEY UPDATE role=VALUES(role),status='active',last_event_at=NOW()""",
        (line_user_id, role),
    )


def apply_role(connection, line_user_id: str, role: str) -> None:
    """Own the role command transaction so transports cannot bypass it."""
    try:
        connection.begin()
        with connection.cursor() as cursor:
            assign_role(cursor, line_user_id, role)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


__all__ = ["activate_follow", "apply_role", "assign_role", "block_unfollow", "cancel_pending_onboarding"]
