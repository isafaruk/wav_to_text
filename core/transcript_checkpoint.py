"""An append-only UTF-8 recovery copy, separate from the final transcript."""

import os
from pathlib import Path
from uuid import uuid4


class TranscriptCheckpoint:
    def __init__(self, source):
        source = Path(source)
        self.path = source.with_name(f"{source.stem}.{uuid4().hex[:12]}.partial.txt")
        self.created = False

    def append(self, text):
        if not text:
            return
        with self.path.open("a" if self.created else "x", encoding="utf-8") as output:
            if not self.created:
                self.created = True
                output.write("[KISMİ METİN — işlem tamamlanmamış olabilir.]\n\n")
            output.write(text)
            output.flush()
            os.fsync(output.fileno())

    def discard(self):
        if self.created:
            self.path.unlink(missing_ok=True)
