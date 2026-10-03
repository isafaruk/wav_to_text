"""Keep native speech libraries outside the GUI's process and DLL namespace."""

from contextlib import contextmanager
import multiprocessing
import time

from core.job_control import ConversionCancelled


class LocalEngineError(RuntimeError):
    pass


def _serve(connection, options):
    # Import here: the spawned interpreter must not import a GUI toolkit.
    from core.engines import _local_whisper, _vosk

    try:
        transcribe = _vosk(options) if options.engine == "vosk" else _local_whisper(options)
        connection.send(("ready", None))
        while True:
            audio = connection.recv()
            if audio is None:
                break
            if isinstance(audio, str):
                last_progress = -1

                def progress(value):
                    nonlocal last_progress
                    value = max(0, min(99, int(value)))
                    if value > last_progress:
                        connection.send(("progress", value))
                        last_progress = value

                progress(0)
                last_event_time = 0

                def event(data):
                    nonlocal last_event_time
                    now = time.monotonic()
                    # Vosk emits many blocks; text is always delivered immediately.
                    if "append_text" in data or now - last_event_time >= 0.25:
                        connection.send(("event", data))
                        if "processed_seconds" in data:
                            last_event_time = now

                text = transcribe(audio, progress_callback=progress, event_callback=event)
            else:
                text = transcribe(audio)
            connection.send(("text", text))
    except EOFError:
        pass
    except Exception as exc:
        try:
            connection.send(("error", str(exc)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


def _crashed(process):
    process.join(timeout=1)
    code = process.exitcode
    detail = "0x{0:08X}".format(code & 0xFFFFFFFF) if code is not None else "bilinmiyor"
    return LocalEngineError(
        "Yerel tanıma motoru beklenmedik biçimde kapandı ({0}). "
        "CPU ve küçük bir model deneyin; sürücü ve çalışma ortamını kontrol edin.".format(detail))


def _receive(connection, process, expected, progress_callback=None, control=None):
    try:
        while True:
            if control is not None:
                control.check()
            while not connection.poll(0.1):
                if control is not None:
                    control.check()
                if not process.is_alive():
                    raise _crashed(process)
            kind, value = connection.recv()
            if kind == "event":
                if control is not None:
                    control.emit(**value)
                continue
            if kind != "progress":
                break
            if progress_callback is not None:
                progress_callback(value)
    except (EOFError, OSError) as exc:
        raise _crashed(process) from exc
    if kind == "error":
        raise LocalEngineError(value)
    if kind != expected:
        raise LocalEngineError("Tanıma motorundan beklenmeyen yanıt alındı.")
    return value


@contextmanager
def local_session(options, progress_callback=None, control=None):
    """Start one model process, reuse it for all chunks, always release it."""
    context = multiprocessing.get_context("spawn")
    connection, child_connection = context.Pipe()
    process = context.Process(target=_serve, args=(child_connection, options), daemon=True)
    started = False
    interrupted = False
    try:
        if control is not None:
            control.check()
        process.start()
        started = True
        child_connection.close()
        _receive(connection, process, "ready", control=control)
        if control is not None:
            control.emit(phase="transcribing")

        def transcribe(audio):
            if control is not None:
                control.check()
            try:
                connection.send(audio)
            except (BrokenPipeError, EOFError, OSError) as exc:
                raise _crashed(process) from exc
            return _receive(connection, process, "text", progress_callback, control)

        yield transcribe
    except ConversionCancelled:
        interrupted = True
        raise
    finally:
        child_connection.close()
        if started:
            if interrupted and process.is_alive():
                process.terminate()
            try:
                if process.is_alive():
                    connection.send(None)
            except (BrokenPipeError, EOFError, OSError):
                pass
            process.join(timeout=3)
            if process.is_alive():
                process.terminate()
                process.join()
            process.close()
        connection.close()
