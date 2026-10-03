"""Prepare local audio/video files for transcription, without Qt dependencies."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import wave
from time import monotonic

from imageio_ffmpeg import get_ffmpeg_exe

CONVERSION_TIMEOUT_SECONDS = 600


class MediaConversionError(Exception):
    """The input could not be prepared as a supported PCM WAV file."""


def _is_pcm_wav(path):
    try:
        with wave.open(str(path), "rb") as audio:
            return (
                audio.getcomptype() == "NONE"
                and audio.getnchannels() in (1, 2)
                and audio.getsampwidth() in (1, 2, 3, 4)
            )
    except (wave.Error, EOFError):
        return False


@contextmanager
def prepare_wav(file_path, *, control=None):
    """Yield a PCM WAV path, keeping converted audio alive only in this context.

    Existing mono/stereo PCM WAV files are read directly. Other media is decoded
    to mono, 16 kHz, 16-bit PCM using its first audio stream. Temporary files are
    removed on success and failure; the original file is never modified.
    """
    if control is not None:
        control.check()
    source = Path(file_path).resolve(strict=True)
    if not source.is_file():
        raise MediaConversionError("Lütfen bir ses veya video dosyası seçiniz.")
    if _is_pcm_wav(source):
        yield str(source)
        return

    try:
        ffmpeg = get_ffmpeg_exe()
    except RuntimeError as exc:
        raise MediaConversionError(
            "Ses dönüştürücü bulunamadı. Proje bağımlılıklarını "
            "'python -m pip install -r requirements.txt' ile yükleyiniz."
        ) from exc

    with TemporaryDirectory(prefix="wav_to_text_media_") as temp_dir:
        wav_path = Path(temp_dir) / "audio.wav"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
            "-i", str(source), "-map", "0:a:0", "-vn",
            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path),
        ]
        try:
            if control is None:
                subprocess.run(
                    command, check=True, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    timeout=CONVERSION_TIMEOUT_SECONDS,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                with subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                ) as process:
                    deadline = monotonic() + CONVERSION_TIMEOUT_SECONDS
                    try:
                        while True:
                            control.check()
                            if monotonic() >= deadline:
                                raise subprocess.TimeoutExpired(command, CONVERSION_TIMEOUT_SECONDS)
                            try:
                                process.communicate(timeout=0.2)
                                break
                            except subprocess.TimeoutExpired:
                                continue
                        control.check()
                        if process.returncode:
                            raise subprocess.CalledProcessError(process.returncode, command)
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.communicate()
        except subprocess.TimeoutExpired as exc:
            raise MediaConversionError("WAV hazırlama işlemi zaman aşımına uğradı.") from exc
        except subprocess.CalledProcessError as exc:
            raise MediaConversionError(
                "Dosya WAV biçimine dönüştürülemedi. Dosya bozuk, "
                "desteklenmiyor veya ses kanalı içermiyor olabilir."
            ) from exc
        except OSError as exc:
            raise MediaConversionError("Ses dönüştürücü başlatılamadı: {0}".format(exc)) from exc
        yield str(wav_path)
