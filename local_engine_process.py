"""Keep native speech libraries outside the GUI's process and DLL namespace."""

from contextlib import contextmanager
import multiprocessing


class LocalEngineError(RuntimeError):
    pass


def _serve(connection, options):
    # Import here: the spawned interpreter must not import a GUI toolkit.
    from engines import _local_whisper, _vosk

    try:
        transcribe = _vosk(options) if options.engine == "vosk" else _local_whisper(options)
        connection.send(("ready", None))
        while True:
            audio = connection.recv()
            if audio is None:
                break
            connection.send(("text", transcribe(audio)))
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


def _receive(connection, process, expected):
    try:
        while not connection.poll(0.1):
            if not process.is_alive():
                raise _crashed(process)
        kind, value = connection.recv()
    except (EOFError, OSError) as exc:
        raise _crashed(process) from exc
    if kind == "error":
        raise LocalEngineError(value)
    if kind != expected:
        raise LocalEngineError("Tanıma motorundan beklenmeyen yanıt alındı.")
    return value


@contextmanager
def local_session(options):
    """Start one model process, reuse it for all chunks, always release it."""
    context = multiprocessing.get_context("spawn")
    connection, child_connection = context.Pipe()
    process = context.Process(target=_serve, args=(child_connection, options), daemon=True)
    started = False
    try:
        process.start()
        started = True
        child_connection.close()
        _receive(connection, process, "ready")

        def transcribe(audio):
            try:
                connection.send(audio)
            except (BrokenPipeError, EOFError, OSError) as exc:
                raise _crashed(process) from exc
            return _receive(connection, process, "text")

        yield transcribe
    finally:
        child_connection.close()
        if started:
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
