import json
from typing import Any
from uuid import uuid4

from app.db.database import get_connection
from app.services import job_service

COMMAND_LEASE_SECONDS = 30
MAX_COMMAND_RETRIES = 3


def register_device(payload: dict[str, Any]) -> dict[str, Any]:
    device_id = str(payload.get("device_id") or "cores3-dev-001")
    name = payload.get("name") or "M5Stack CoreS3"
    firmware_version = payload.get("firmware_version") or "dev"
    hardware_model = payload.get("hardware_model") or "m5stack-cores3"
    ip_address = payload.get("ip_address")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO device (
                device_id, name, firmware_version, hardware_model, ip_address, status
            )
            VALUES (?, ?, ?, ?, ?, 'online')
            ON CONFLICT(device_id) DO UPDATE SET
                name = excluded.name,
                firmware_version = excluded.firmware_version,
                hardware_model = excluded.hardware_model,
                ip_address = excluded.ip_address,
                status = 'online',
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """,
            (device_id, name, firmware_version, hardware_model, ip_address),
        )

    return {
        "device_id": device_id,
        "name": name,
        "status": "online",
        "command_poll_seconds": 5,
    }


def update_heartbeat(payload: dict[str, Any]) -> dict[str, Any]:
    device_id = str(payload.get("device_id") or "cores3-dev-001")
    state = payload.get("state")
    battery_percent = payload.get("battery_percent")
    rssi = payload.get("rssi")
    free_heap = payload.get("free_heap")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO device (device_id, status, last_seen_at, updated_at)
            VALUES (?, 'online', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(device_id) DO UPDATE SET
                status = 'online',
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """,
            (device_id,),
        )
        conn.execute(
            """
            INSERT INTO device_status_log (
                device_id, state, battery_percent, rssi, free_heap, payload
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                state,
                battery_percent,
                rssi,
                free_heap,
                json.dumps(payload, ensure_ascii=False),
            ),
        )

    return {"device_id": device_id, "status": "online"}


def record_device_status(payload: dict[str, Any]) -> dict[str, Any]:
    device_id = str(payload.get("device_id") or "cores3-dev-001")
    state = payload.get("state")
    battery_percent = payload.get("battery_percent")
    rssi = payload.get("rssi")
    free_heap = payload.get("free_heap")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO device_status_log (
                device_id, state, battery_percent, rssi, free_heap, payload
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                state,
                battery_percent,
                rssi,
                free_heap,
                json.dumps(payload, ensure_ascii=False),
            ),
        )

    return {"device_id": device_id, "recorded": True}


def record_device_event(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("event_type") or "unknown")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO device_event (device_id, event_type, payload)
            VALUES (?, ?, ?)
            """,
            (device_id, event_type, json.dumps(payload, ensure_ascii=False)),
        )

    return {"device_id": device_id, "event_type": event_type, "recorded": True}


def enqueue_device_command(
    device_id: str,
    command_type: str,
    payload: dict[str, Any],
    job_id: str | None = None,
    return_command_id: bool = False,
) -> int | tuple[str, int]:
    cmd_id = f"cmd_{uuid4().hex}"
    command_job_id = job_id or payload.get("job_id")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO device_command (
                cmd_id, device_id, job_id, command_type, payload, status, retry_count, expire_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', 0, datetime('now', '+120 seconds'))
            """,
            (cmd_id, device_id, command_job_id, command_type, json.dumps(payload, ensure_ascii=False)),
        )
        conn.execute(
            """
            INSERT INTO device_command_delivery_log (cmd_id, device_id, event_type, detail_json)
            VALUES (?, ?, 'created', ?)
            """,
            (cmd_id, device_id, json.dumps({"type": command_type}, ensure_ascii=False)),
        )
        row_id = int(cursor.lastrowid)
        return (cmd_id, row_id) if return_command_id else row_id


def get_pending_device_commands(device_id: str, limit: int = 5) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 20))
    with get_connection() as conn:
        _requeue_expired_commands(conn, device_id)
        rows = conn.execute(
            """
            SELECT id, cmd_id, command_type, payload, created_at
            FROM device_command
            WHERE device_id = ? AND status = 'pending'
              AND retry_count < ?
              AND (expire_at IS NULL OR expire_at > CURRENT_TIMESTAMP)
            ORDER BY id ASC
            LIMIT ?
            """,
            (device_id, MAX_COMMAND_RETRIES, safe_limit),
        ).fetchall()

        command_updates: list[tuple[str, str, int]] = []
        for row in rows:
            cmd_id = row["cmd_id"] or f"cmd_legacy_{row['id']}"
            command_updates.append((cmd_id, device_id, row["id"]))

        if command_updates:
            command_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in command_ids)
            conn.execute(
                f"""
                UPDATE device_command
                SET status = 'sent',
                    delivered_at = CURRENT_TIMESTAMP,
                    lease_until = datetime('now', '+{COMMAND_LEASE_SECONDS} seconds'),
                    retry_count = retry_count + 1
                WHERE id IN ({placeholders})
                """,
                command_ids,
            )
            for cmd_id, row_device_id, _ in command_updates:
                conn.execute(
                    """
                    INSERT INTO device_command_delivery_log (cmd_id, device_id, event_type, detail_json)
                    VALUES (?, ?, 'delivered', ?)
                    """,
                    (
                        cmd_id,
                        row_device_id,
                        json.dumps({"lease_seconds": COMMAND_LEASE_SECONDS}, ensure_ascii=False),
                    ),
                )

        leased_rows = conn.execute(
            """
            SELECT id, cmd_id, command_type, payload, created_at, lease_until
            FROM device_command
            WHERE id IN ({})
            ORDER BY id ASC
            """.format(",".join("?" for _ in rows) or "NULL"),
            [row["id"] for row in rows],
        ).fetchall() if rows else []

    commands: list[dict[str, Any]] = []
    for row in leased_rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        commands.append(
            {
                "id": row["id"],
                "cmd_id": row["cmd_id"],
                "type": row["command_type"],
                "payload": payload,
                "lease_until": row["lease_until"],
                "created_at": row["created_at"],
            }
        )
    return commands


def ack_device_command(device_id: str, cmd_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "success").lower()
    ok = status in {"success", "ok", "ack", "acked"}
    event_type = "ack" if ok else "failed"
    error_code = None if ok else str(payload.get("error_code") or "COMMAND_FAILED")
    error_message = None if ok else str(payload.get("error_message") or "")
    completed_job_id: str | None = None

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, cmd_id, status
            FROM device_command
            WHERE device_id = ?
              AND (cmd_id = ? OR CAST(id AS TEXT) = ?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (device_id, cmd_id, cmd_id),
        ).fetchone()
        if row is None:
            return {"device_id": device_id, "cmd_id": cmd_id, "acked": False, "reason": "not_found"}

        final_status = "ack" if ok else "failed"
        conn.execute(
            """
            UPDATE device_command
            SET status = ?,
                acked_at = CASE WHEN ? = 'ack' THEN CURRENT_TIMESTAMP ELSE acked_at END,
                completed_at = CURRENT_TIMESTAMP,
                error_code = ?,
                error_message = ?
            WHERE id = ?
            """,
            (final_status, final_status, error_code, error_message, row["id"]),
        )
        conn.execute(
            """
            INSERT INTO device_command_delivery_log (cmd_id, device_id, event_type, detail_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                row["cmd_id"],
                device_id,
                event_type,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        job_id = conn.execute(
            "SELECT job_id FROM device_command WHERE id = ?",
            (row["id"],),
        ).fetchone()["job_id"]
        if ok and job_id:
            completed_job_id = str(job_id)

    if completed_job_id:
        job_service.mark_completed(completed_job_id)

    return {
        "device_id": device_id,
        "cmd_id": row["cmd_id"],
        "acked": ok,
        "status": final_status,
    }


def _requeue_expired_commands(conn, device_id: str) -> None:
    expired_rows = conn.execute(
        """
        SELECT id, cmd_id, retry_count
        FROM device_command
        WHERE device_id = ?
          AND status = 'sent'
          AND lease_until IS NOT NULL
          AND lease_until <= CURRENT_TIMESTAMP
        """,
        (device_id,),
    ).fetchall()

    for row in expired_rows:
        if int(row["retry_count"] or 0) >= MAX_COMMAND_RETRIES:
            conn.execute(
                """
                UPDATE device_command
                    SET status = 'expired',
                    error_code = 'LEASE_EXPIRED',
                    error_message = 'command lease expired too many times',
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (row["id"],),
            )
            event_type = "expired_failed"
        else:
            conn.execute(
                """
                UPDATE device_command
                SET status = 'pending',
                    lease_until = NULL
                WHERE id = ?
                """,
                (row["id"],),
            )
            event_type = "lease_expired"

        conn.execute(
            """
            INSERT INTO device_command_delivery_log (cmd_id, device_id, event_type, detail_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                row["cmd_id"],
                device_id,
                event_type,
                json.dumps({"retry_count": row["retry_count"]}, ensure_ascii=False),
            ),
        )

    conn.execute(
        """
        UPDATE device_command
        SET status = 'expired',
            error_code = 'COMMAND_EXPIRED',
            error_message = 'command expired before delivery',
            completed_at = CURRENT_TIMESTAMP
        WHERE device_id = ?
          AND status = 'pending'
          AND expire_at IS NOT NULL
          AND expire_at <= CURRENT_TIMESTAMP
        """,
        (device_id,),
    )
