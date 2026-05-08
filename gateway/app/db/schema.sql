CREATE TABLE IF NOT EXISTS device (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT UNIQUE NOT NULL,
    name TEXT,
    firmware_version TEXT,
    hardware_model TEXT,
    ip_address TEXT,
    status TEXT DEFAULT 'registered',
    registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS device_status_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    state TEXT,
    battery_percent INTEGER,
    rssi INTEGER,
    free_heap INTEGER,
    payload TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS device_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS device_command (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cmd_id TEXT UNIQUE,
    device_id TEXT NOT NULL,
    job_id TEXT,
    command_type TEXT NOT NULL,
    payload TEXT,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    delivered_at TEXT,
    lease_until TEXT,
    acked_at TEXT,
    completed_at TEXT,
    expire_at TEXT,
    error_code TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_device_command_device_status
ON device_command(device_id, status);

CREATE TABLE IF NOT EXISTS device_command_delivery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cmd_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_command_delivery_log_cmd_id
ON device_command_delivery_log(cmd_id);

CREATE TABLE IF NOT EXISTS device_audio_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    device_id TEXT NOT NULL,
    audio_path TEXT,
    sample_rate INTEGER,
    channels INTEGER,
    sample_format TEXT,
    duration_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'accepted',
    stt_text TEXT,
    llm_text TEXT,
    tts_audio_url TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_device_audio_job_device_status
ON device_audio_job(device_id, status);

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
);

CREATE INDEX IF NOT EXISTS idx_audio_chat_job_device_status
ON audio_chat_job(device_id, status);

CREATE TABLE IF NOT EXISTS audio_asset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT UNIQUE NOT NULL,
    device_id TEXT,
    kind TEXT NOT NULL,
    original_filename TEXT,
    content_type TEXT,
    file_path TEXT NOT NULL,
    file_url TEXT NOT NULL,
    size_bytes INTEGER,
    stt_provider TEXT,
    stt_text TEXT,
    stt_latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audio_chat_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    state TEXT,
    user_asset_id TEXT,
    reply_asset_id TEXT,
    user_audio_url TEXT,
    reply_audio_url TEXT,
    user_text TEXT,
    assistant_text TEXT,
    tts_text TEXT,
    stt_provider TEXT,
    stt_latency_ms INTEGER,
    stt_confidence REAL,
    llm_provider TEXT,
    llm_model TEXT,
    llm_latency_ms INTEGER,
    llm_finish_reason TEXT,
    tts_provider TEXT,
    tts_latency_ms INTEGER,
    tts_sample_rate INTEGER,
    tts_size_bytes INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

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
);

CREATE INDEX IF NOT EXISTS idx_realtime_voice_session_device_status
ON realtime_voice_session(device_id, status);
