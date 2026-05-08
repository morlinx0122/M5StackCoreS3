import os
import sqlite3
from pathlib import Path

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/deepnexus_gateway.db")


def get_db_path() -> Path:
    return Path(DATABASE_PATH)


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    with get_connection() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        ensure_audio_asset_columns(conn)
        ensure_audio_chat_log_columns(conn)
        ensure_device_command_columns(conn)
        ensure_device_audio_job_columns(conn)
        ensure_audio_chat_job_columns(conn)
        ensure_realtime_voice_session_columns(conn)


def ensure_audio_asset_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(audio_asset)").fetchall()
    }
    migrations = {
        "stt_provider": "ALTER TABLE audio_asset ADD COLUMN stt_provider TEXT",
        "stt_text": "ALTER TABLE audio_asset ADD COLUMN stt_text TEXT",
        "stt_latency_ms": "ALTER TABLE audio_asset ADD COLUMN stt_latency_ms INTEGER",
    }

    for column, statement in migrations.items():
        if column not in existing_columns:
            conn.execute(statement)


def ensure_audio_chat_log_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(audio_chat_log)").fetchall()
    }
    migrations = {
        "tts_text": "ALTER TABLE audio_chat_log ADD COLUMN tts_text TEXT",
    }

    for column, statement in migrations.items():
        if column not in existing_columns:
            conn.execute(statement)


def ensure_device_command_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(device_command)").fetchall()
    }
    migrations = {
        "cmd_id": "ALTER TABLE device_command ADD COLUMN cmd_id TEXT",
        "job_id": "ALTER TABLE device_command ADD COLUMN job_id TEXT",
        "retry_count": "ALTER TABLE device_command ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
        "lease_until": "ALTER TABLE device_command ADD COLUMN lease_until TEXT",
        "acked_at": "ALTER TABLE device_command ADD COLUMN acked_at TEXT",
        "expire_at": "ALTER TABLE device_command ADD COLUMN expire_at TEXT",
        "error_code": "ALTER TABLE device_command ADD COLUMN error_code TEXT",
        "error_message": "ALTER TABLE device_command ADD COLUMN error_message TEXT",
    }

    for column, statement in migrations.items():
        if column not in existing_columns:
            conn.execute(statement)

    conn.execute(
        """
        UPDATE device_command
        SET cmd_id = 'cmd_' || lower(hex(randomblob(16)))
        WHERE cmd_id IS NULL OR cmd_id = ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_device_command_cmd_id
        ON device_command(cmd_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_device_command_device_status
        ON device_command(device_id, status)
        """
    )


def ensure_device_audio_job_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(device_audio_job)").fetchall()
    }
    migrations = {
        "duration_ms": "ALTER TABLE device_audio_job ADD COLUMN duration_ms INTEGER",
        "error_code": "ALTER TABLE device_audio_job ADD COLUMN error_code TEXT",
        "error_message": "ALTER TABLE device_audio_job ADD COLUMN error_message TEXT",
    }

    for column, statement in migrations.items():
        if column not in existing_columns:
            conn.execute(statement)


def ensure_audio_chat_job_columns(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audio_chat_job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'accepted',
            input_audio_path TEXT,
            input_audio_url TEXT,
            user_text TEXT,
            assistant_text TEXT,
            reply_audio_path TEXT,
            reply_audio_url TEXT,
            stt_provider TEXT,
            stt_model TEXT,
            llm_provider TEXT,
            llm_model TEXT,
            tts_provider TEXT,
            tts_model TEXT,
            tts_voice TEXT,
            stt_latency_ms INTEGER,
            llm_latency_ms INTEGER,
            tts_latency_ms INTEGER,
            total_latency_ms INTEGER,
            command_id TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
        """
    )
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(audio_chat_job)").fetchall()
    }
    migrations = {
        "input_audio_path": "ALTER TABLE audio_chat_job ADD COLUMN input_audio_path TEXT",
        "input_audio_url": "ALTER TABLE audio_chat_job ADD COLUMN input_audio_url TEXT",
        "user_text": "ALTER TABLE audio_chat_job ADD COLUMN user_text TEXT",
        "assistant_text": "ALTER TABLE audio_chat_job ADD COLUMN assistant_text TEXT",
        "reply_audio_path": "ALTER TABLE audio_chat_job ADD COLUMN reply_audio_path TEXT",
        "reply_audio_url": "ALTER TABLE audio_chat_job ADD COLUMN reply_audio_url TEXT",
        "stt_provider": "ALTER TABLE audio_chat_job ADD COLUMN stt_provider TEXT",
        "stt_model": "ALTER TABLE audio_chat_job ADD COLUMN stt_model TEXT",
        "llm_provider": "ALTER TABLE audio_chat_job ADD COLUMN llm_provider TEXT",
        "llm_model": "ALTER TABLE audio_chat_job ADD COLUMN llm_model TEXT",
        "tts_provider": "ALTER TABLE audio_chat_job ADD COLUMN tts_provider TEXT",
        "tts_model": "ALTER TABLE audio_chat_job ADD COLUMN tts_model TEXT",
        "tts_voice": "ALTER TABLE audio_chat_job ADD COLUMN tts_voice TEXT",
        "stt_latency_ms": "ALTER TABLE audio_chat_job ADD COLUMN stt_latency_ms INTEGER",
        "llm_latency_ms": "ALTER TABLE audio_chat_job ADD COLUMN llm_latency_ms INTEGER",
        "tts_latency_ms": "ALTER TABLE audio_chat_job ADD COLUMN tts_latency_ms INTEGER",
        "total_latency_ms": "ALTER TABLE audio_chat_job ADD COLUMN total_latency_ms INTEGER",
        "command_id": "ALTER TABLE audio_chat_job ADD COLUMN command_id TEXT",
        "error_code": "ALTER TABLE audio_chat_job ADD COLUMN error_code TEXT",
        "error_message": "ALTER TABLE audio_chat_job ADD COLUMN error_message TEXT",
        "completed_at": "ALTER TABLE audio_chat_job ADD COLUMN completed_at TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing_columns:
            conn.execute(statement)

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audio_chat_job_device_status
        ON audio_chat_job(device_id, status)
        """
    )


def ensure_realtime_voice_session_columns(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS realtime_voice_session (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'listening',
            partial_text TEXT,
            final_text TEXT,
            assistant_text TEXT,
            intent TEXT,
            fast_intent_hit INTEGER DEFAULT 0,
            user_emotion TEXT,
            user_event TEXT,
            stt_provider TEXT,
            stt_streaming_model TEXT,
            stt_final_model TEXT,
            llm_provider TEXT,
            llm_model TEXT,
            tts_provider TEXT,
            tts_model TEXT,
            tts_voice TEXT,
            first_audio_in_at TEXT,
            speech_end_at TEXT,
            stt_final_at TEXT,
            fast_intent_done_at TEXT,
            llm_first_token_at TEXT,
            llm_first_sentence_at TEXT,
            tts_first_audio_at TEXT,
            playback_start_at TEXT,
            playback_end_at TEXT,
            first_response_latency_ms INTEGER,
            total_latency_ms INTEGER,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(realtime_voice_session)").fetchall()
    }
    migrations = {
        "partial_text": "ALTER TABLE realtime_voice_session ADD COLUMN partial_text TEXT",
        "final_text": "ALTER TABLE realtime_voice_session ADD COLUMN final_text TEXT",
        "assistant_text": "ALTER TABLE realtime_voice_session ADD COLUMN assistant_text TEXT",
        "intent": "ALTER TABLE realtime_voice_session ADD COLUMN intent TEXT",
        "fast_intent_hit": "ALTER TABLE realtime_voice_session ADD COLUMN fast_intent_hit INTEGER DEFAULT 0",
        "user_emotion": "ALTER TABLE realtime_voice_session ADD COLUMN user_emotion TEXT",
        "user_event": "ALTER TABLE realtime_voice_session ADD COLUMN user_event TEXT",
        "stt_provider": "ALTER TABLE realtime_voice_session ADD COLUMN stt_provider TEXT",
        "stt_streaming_model": "ALTER TABLE realtime_voice_session ADD COLUMN stt_streaming_model TEXT",
        "stt_final_model": "ALTER TABLE realtime_voice_session ADD COLUMN stt_final_model TEXT",
        "llm_provider": "ALTER TABLE realtime_voice_session ADD COLUMN llm_provider TEXT",
        "llm_model": "ALTER TABLE realtime_voice_session ADD COLUMN llm_model TEXT",
        "tts_provider": "ALTER TABLE realtime_voice_session ADD COLUMN tts_provider TEXT",
        "tts_model": "ALTER TABLE realtime_voice_session ADD COLUMN tts_model TEXT",
        "tts_voice": "ALTER TABLE realtime_voice_session ADD COLUMN tts_voice TEXT",
        "first_audio_in_at": "ALTER TABLE realtime_voice_session ADD COLUMN first_audio_in_at TEXT",
        "speech_end_at": "ALTER TABLE realtime_voice_session ADD COLUMN speech_end_at TEXT",
        "stt_final_at": "ALTER TABLE realtime_voice_session ADD COLUMN stt_final_at TEXT",
        "fast_intent_done_at": "ALTER TABLE realtime_voice_session ADD COLUMN fast_intent_done_at TEXT",
        "llm_first_token_at": "ALTER TABLE realtime_voice_session ADD COLUMN llm_first_token_at TEXT",
        "llm_first_sentence_at": "ALTER TABLE realtime_voice_session ADD COLUMN llm_first_sentence_at TEXT",
        "tts_first_audio_at": "ALTER TABLE realtime_voice_session ADD COLUMN tts_first_audio_at TEXT",
        "playback_start_at": "ALTER TABLE realtime_voice_session ADD COLUMN playback_start_at TEXT",
        "playback_end_at": "ALTER TABLE realtime_voice_session ADD COLUMN playback_end_at TEXT",
        "first_response_latency_ms": (
            "ALTER TABLE realtime_voice_session ADD COLUMN first_response_latency_ms INTEGER"
        ),
        "total_latency_ms": "ALTER TABLE realtime_voice_session ADD COLUMN total_latency_ms INTEGER",
        "error_code": "ALTER TABLE realtime_voice_session ADD COLUMN error_code TEXT",
        "error_message": "ALTER TABLE realtime_voice_session ADD COLUMN error_message TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing_columns:
            conn.execute(statement)

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_realtime_voice_session_device_status
        ON realtime_voice_session(device_id, status)
        """
    )
