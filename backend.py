"""WAV conversion and output files, independent of the user interface."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import speech_recognition as sr
from audio_runtime import AudioSegment
from pydub.utils import make_chunks

from audio_policy import (CLOUD_UPLOAD_ENGINES, LOCAL_ENGINES, UPLOAD_SAMPLE_RATE,
                          UPLOAD_SAMPLE_WIDTH, chunk_duration_ms, request_timeout)
from engines import RecognitionOptions, recognition_session, validate_options
from transcript_format import format_paragraphs


@dataclass(frozen=True)
class ConversionResult:
    status: str
    text: str
    successful_chunks: int
    total_chunks: int
    output_path: str | None
    errors: tuple[str, ...] = ()


def convert_audio(
    file_path: str,
    progress_callback: Callable[[int], None] | None = None,
    *,
    output_source_path: str | None = None,
    recognition_options: RecognitionOptions | None = None,
) -> ConversionResult:
    """Convert a WAV file and save its transcript.

    The optional callback receives processed-chunk or local-engine progress.
    Local engines receive a file path in their own process; their result counts
    as one recognition unit, regardless of the number of transcript paragraphs.
    Recognition failures are represented in the result; file and unexpected
    errors propagate to the caller. This function runs synchronously.
    For temporary WAV inputs, output_source_path selects the original media
    path whose directory and stem are used for the transcript.
    recognition_options selects the engine; omitted options preserve Google.
    """
    options = recognition_options or RecognitionOptions()
    validate_options(options)
    local = options.engine in LOCAL_ENGINES
    r = sr.Recognizer()
    r.operation_timeout = request_timeout(options.engine)
    if local:
        # Only inspect the header here. Native decoders read the file in the child.
        with sr.AudioFile(file_path) as source:
            chunks = [str(Path(file_path).resolve())] if source.FRAME_COUNT else []
    else:
        with open(file_path, "rb") as input_file:
            myaudio = AudioSegment.from_file(input_file, 'wav')
        if options.engine in CLOUD_UPLOAD_ENGINES:
            myaudio = myaudio.set_channels(1).set_frame_rate(UPLOAD_SAMPLE_RATE).set_sample_width(UPLOAD_SAMPLE_WIDTH)
        chunks = make_chunks(myaudio, chunk_duration_ms(options.engine))
    if not chunks:
        return ConversionResult("failed", "", 0, 0, None,
                                ("WAV dosyası ses verisi içermiyor.",))
    text_parts = []
    successful_chunks = 0
    errors = []
    last_progress = -1

    def local_progress(value):
        nonlocal last_progress
        # 100 means the complete response has arrived, not just the last segment.
        value = max(0, min(99, int(value)))
        if progress_callback is not None and value > last_progress:
            progress_callback(value)
            last_progress = value

    session_args = {"progress_callback": local_progress} if local else {}
    with recognition_session(r, options, **session_args) as transcribe, \
            (nullcontext(None) if local else TemporaryDirectory(prefix="wav_to_text_")) as temp_dir:
        for i, chunk in enumerate(chunks):
            if local:
                audio = chunk
            else:
                chunk_name = os.path.join(temp_dir, 'chunk{0}.wav'.format(i + 1))
                with open(chunk_name, "wb") as chunk_file:
                    chunk.export(chunk_file, format='wav')
                with sr.AudioFile(chunk_name) as source:
                    audio = r.record(source)
            try:
                transcript = transcribe(audio).strip()
                if not transcript:
                    raise sr.UnknownValueError()
            except sr.UnknownValueError:
                message = "{0}. parça: Ses algılanamadı.".format(i + 1)
                errors.append(message)
                text_parts.append("[{0}]".format(message))
            except TimeoutError:
                message = "{0}. parça: Tanıma isteği zaman aşımına uğradı.".format(i + 1)
                errors.append(message)
                text_parts.append("[{0}]".format(message))
            except sr.RequestError as e:
                message = "{0}. parça: Tanıma başarısız; {1}".format(i + 1, e)
                errors.append(message)
                text_parts.append("[{0}]".format(message))
            else:
                text_parts.append(format_paragraphs(transcript))
                successful_chunks += 1
            if progress_callback is not None:
                progress_callback((i + 1) * 100 // len(chunks))

    # Keep failed requests in place, independently of paragraph formatting.
    text = "\n\n".join(text_parts)
    if not successful_chunks:
        return ConversionResult("failed", text, 0, len(chunks), None, tuple(errors))

    output_base = os.path.splitext(output_source_path or file_path)[0]
    dosya_adi = output_base + ".txt"

    # Dosya ismi varsa farklı bir isim oluşturur
    i = 1
    while os.path.exists(dosya_adi):
        dosya_adi = output_base + "({0}).txt".format(i)
        i += 1

    with open(dosya_adi, "w", encoding="utf-8") as dosya:
        dosya.write(text)
    status = "success" if successful_chunks == len(chunks) else "partial"
    return ConversionResult(status, text, successful_chunks, len(chunks),
                            dosya_adi, tuple(errors))
