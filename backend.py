"""WAV conversion and output files, independent of the user interface."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from tempfile import TemporaryDirectory

import speech_recognition as sr
from pydub import AudioSegment
from pydub.utils import make_chunks

from engines import RecognitionOptions, recognition_session

REQUEST_TIMEOUT_SECONDS = 30


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

    The optional callback receives the percentage after each processed chunk.
    Recognition failures are represented in the result; file and unexpected
    errors propagate to the caller. This function runs synchronously.
    For temporary WAV inputs, output_source_path selects the original media
    path whose directory and stem are used for the transcript.
    recognition_options selects the engine; omitted options preserve Google.
    """
    r = sr.Recognizer()
    r.operation_timeout = REQUEST_TIMEOUT_SECONDS
    with open(file_path, "rb") as input_file:
        myaudio = AudioSegment.from_file(input_file, 'wav')
    chunk_length_ms = 50000  # pydub calculates in milliseconds
    chunks = make_chunks(myaudio, chunk_length_ms)
    if not chunks:
        return ConversionResult("failed", "", 0, 0, None,
                                ("WAV dosyası ses verisi içermiyor.",))
    text_parts = []
    successful_chunks = 0
    errors = []
    with recognition_session(r, recognition_options or RecognitionOptions()) as transcribe, \
            TemporaryDirectory(prefix="wav_to_text_") as temp_dir:
        for i, chunk in enumerate(chunks):
            chunk_name = os.path.join(temp_dir, 'chunk{0}.wav'.format(i + 1))
            with open(chunk_name, "wb") as chunk_file:
                chunk.export(chunk_file, format='wav')
            with sr.AudioFile(chunk_name) as source:
                audio = r.record(source)  # read the entire audio file
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
                    text_parts.append(transcript)
                    successful_chunks += 1
            if progress_callback is not None:
                progress_callback((i + 1) * 100 // len(chunks))

    # Keep each 50-second chunk (including failure markers) in its own paragraph.
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

    with open(dosya_adi, "w") as dosya:
        dosya.write(text)
    status = "success" if successful_chunks == len(chunks) else "partial"
    return ConversionResult(status, text, successful_chunks, len(chunks),
                            dosya_adi, tuple(errors))
