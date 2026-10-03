"""Input limits for each engine, measured on the WAV actually uploaded."""

LOCAL_ENGINES = frozenset(("faster_whisper", "whisper", "vosk"))
CLOUD_UPLOAD_ENGINES = frozenset(("groq", "openai"))
UPLOAD_SAMPLE_RATE = 16000
UPLOAD_SAMPLE_WIDTH = 2
# Both direct-upload APIs accept 25 MB; leave room below that limit.
MAX_UPLOAD_BYTES = 24_000_000
PCM_WAV_HEADER_BYTES = 44


def chunk_duration_ms(engine):
    if engine in LOCAL_ENGINES:
        return None
    if engine in CLOUD_UPLOAD_ENGINES:
        bytes_per_second = UPLOAD_SAMPLE_RATE * UPLOAD_SAMPLE_WIDTH
        return (MAX_UPLOAD_BYTES - PCM_WAV_HEADER_BYTES) * 1000 // bytes_per_second
    # Google legacy recognition and Azure's 60-second short-audio endpoint.
    return 50_000


def request_timeout(engine):
    return 180 if engine in CLOUD_UPLOAD_ENGINES else 30
