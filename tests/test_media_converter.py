from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

from core import media_converter
from helpers import ConversionTestCase
from eski.worker import AudioToTextThread


class MediaConverterTests(ConversionTestCase):
    def ffmpeg(self, *args):
        subprocess.run(
            [media_converter.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
             "-nostdin", "-n", *map(str, args)],
            check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def make_audio(self, suffix, codec):
        destination = self.root / ("örnek ses " + suffix)
        self.ffmpeg("-i", self.source, "-c:a", codec, destination)
        return destination

    def make_video(self, with_audio=True):
        destination = self.root / ("video.mp4" if with_audio else "silent.mp4")
        arguments = ["-f", "lavfi", "-i", "color=c=black:s=16x16:r=10:d=0.2"]
        if with_audio:
            arguments += ["-i", self.source, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac"]
        arguments += ["-c:v", "mpeg4", "-shortest", destination]
        self.ffmpeg(*arguments)
        return destination

    def assert_prepared_wav(self, path):
        with wave.open(str(path), "rb") as audio:
            self.assertEqual("NONE", audio.getcomptype())
            self.assertEqual(1, audio.getnchannels())
            self.assertEqual(2, audio.getsampwidth())
            self.assertEqual(16000, audio.getframerate())
            self.assertGreater(audio.getnframes(), 0)
            self.assertTrue(audio.readframes(audio.getnframes()))

    def test_existing_pcm_wav_is_used_without_ffmpeg(self):
        source = self.source.rename(self.source.with_suffix(".WAV"))
        original = source.read_bytes()
        with patch("core.media_converter.get_ffmpeg_exe") as locate:
            with media_converter.prepare_wav(source) as path:
                self.assertEqual(source, Path(path))
        locate.assert_not_called()
        self.assertEqual(original, source.read_bytes())

    def test_real_audio_formats_become_temporary_pcm_wav(self):
        for suffix, codec in [
            (".mp3", "libmp3lame"), (".m4a", "aac"),
            (".flac", "flac"), (".ogg", "libvorbis"),
            (".wav", "pcm_f32le"),
        ]:
            with self.subTest(suffix=suffix):
                source = self.make_audio(suffix, codec)
                original = source.read_bytes()
                with media_converter.prepare_wav(source) as path:
                    self.assert_prepared_wav(path)
                    self.assertNotEqual(source.parent, Path(path).parent)
                self.assertFalse(Path(path).parent.exists())
                self.assertEqual(original, source.read_bytes())

    def test_real_mp4_audio_is_extracted(self):
        source = self.make_video()
        original = source.read_bytes()
        with media_converter.prepare_wav(source) as path:
            self.assert_prepared_wav(path)
        self.assertFalse(Path(path).exists())
        self.assertEqual(original, source.read_bytes())

    def test_format_is_detected_from_content_instead_of_extension(self):
        source = self.make_audio(".mp3", "libmp3lame").rename(self.root / "recording.bin")
        with media_converter.prepare_wav(source) as path:
            self.assert_prepared_wav(path)

    def test_invalid_media_and_video_without_audio_are_rejected_and_cleaned(self):
        invalid = self.root / "not audio.txt"
        invalid.write_text("not audio or video")
        for source in (invalid, self.make_video(with_audio=False)):
            with self.subTest(source=source):
                directories = []

                def temporary_directory(**kwargs):
                    directory = tempfile.TemporaryDirectory(**kwargs)
                    directories.append(Path(directory.name))
                    return directory

                with patch("core.media_converter.TemporaryDirectory", side_effect=temporary_directory):
                    with self.assertRaises(media_converter.MediaConversionError):
                        with media_converter.prepare_wav(source):
                            self.fail("Invalid media must not reach recognition")
                self.assertTrue(directories)
                self.assertTrue(all(not path.exists() for path in directories))
                self.assertTrue(source.exists())

    def test_temporary_wav_is_removed_when_caller_fails(self):
        source = self.make_audio(".mp3", "libmp3lame")
        with self.assertRaisesRegex(RuntimeError, "recognition failed"):
            with media_converter.prepare_wav(source) as path:
                raise RuntimeError("recognition failed")
        self.assertFalse(Path(path).parent.exists())
        self.assertTrue(source.exists())

    def test_converter_timeout_is_reported_and_partial_wav_is_removed(self):
        source = self.root / "recording.mp3"
        source.write_bytes(b"fake mp3")
        destinations = []

        def timeout(command, **kwargs):
            destination = Path(command[-1])
            destinations.append(destination)
            destination.write_bytes(b"partial wav")
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        with patch("core.media_converter.get_ffmpeg_exe", return_value="ffmpeg"), patch(
            "core.media_converter.subprocess.run", side_effect=timeout
        ):
            with self.assertRaisesRegex(media_converter.MediaConversionError, "zaman"):
                with media_converter.prepare_wav(source):
                    self.fail("Timed out conversion must not reach recognition")
        self.assertTrue(destinations)
        self.assertFalse(destinations[0].parent.exists())

    def test_missing_converter_reports_setup_instructions(self):
        source = self.root / "recording.mp3"
        source.write_bytes(b"fake mp3")
        with patch("core.media_converter.get_ffmpeg_exe", side_effect=RuntimeError("missing")):
            with self.assertRaisesRegex(media_converter.MediaConversionError, "requirements.txt"):
                with media_converter.prepare_wav(source):
                    self.fail("Missing converter must not reach recognition")

    def test_mp3_worker_writes_transcript_next_to_original_and_preserves_files(self):
        source = self.make_audio(".mp3", "libmp3lame")
        original = source.read_bytes()
        neighbor_wav = source.with_suffix(".wav")
        neighbor_wav.write_bytes(b"existing user wav")
        worker = AudioToTextThread(str(source))
        results, errors, progress = [], [], []
        worker.done.connect(results.append)
        worker.error.connect(errors.append)
        worker.progress.connect(progress.append)
        worker.run()
        self.assertEqual([], errors)
        self.assertEqual(1, len(results))
        self.assertEqual("success", results[0].status)
        self.assertEqual(source.with_suffix(".txt"), Path(results[0].output_path))
        self.assertEqual("first", Path(results[0].output_path).read_text(encoding="utf-8"))
        self.assertEqual([100], progress)
        self.assertEqual(original, source.read_bytes())
        self.assertEqual(b"existing user wav", neighbor_wav.read_bytes())


if __name__ == "__main__":
    unittest.main()
