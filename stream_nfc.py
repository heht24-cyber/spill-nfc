"""Normalize a UTF-8 stream to NFC with bounded pending-text RAM and disk spill."""
import argparse
import codecs
from contextlib import ExitStack
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from shutil import copyfileobj
import sys
from tempfile import SpooledTemporaryFile
import unicodedata as ud


@lru_cache(maxsize=8192)
def compose(a, b):
    candidate = ud.normalize("NFC", a + b)
    return candidate if len(candidate) == 1 else None


def normalize(source, target, chunk=65536, spill=4096):
    if chunk < 1 or spill < 1:
        raise ValueError("chunk and spill must be positive byte counts")
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    starter = ""
    buckets = {}
    with ExitStack() as resources:
        def boundary(next_starter):
            nonlocal starter
            if not buckets:
                merged = compose(starter, next_starter) if starter and next_starter else None
                if merged:
                    starter = merged
                else:
                    target.write(starter.encode())
                    starter = next_starter
                return
            last_unmerged = 0
            with SpooledTemporaryFile(max_size=spill) as suffix:
                for cls, bucket in sorted(buckets.items()):
                    bucket.seek(0)
                    while block := bucket.read(8192):
                        for char in block.decode("utf-32-le"):
                            merged = compose(starter, char) if starter and last_unmerged < cls else None
                            if merged:
                                starter = merged
                            else:
                                suffix.write(char.encode())
                                last_unmerged = cls
                # A zero-class composition (notably Hangul) may span this boundary.
                merged = (compose(starter, next_starter)
                          if starter and next_starter and not last_unmerged else None)
                if merged:
                    starter = merged
                else:
                    target.write(starter.encode())
                    suffix.seek(0)
                    copyfileobj(suffix, target, length=8192)
                    starter = next_starter
            resources.close()
            buckets.clear()

        while True:
            raw = source.read(chunk)
            for char in decoder.decode(raw, final=not raw):
                for cp in ud.normalize("NFD", char):
                    cls = ud.combining(cp)
                    if not cls:
                        boundary(cp)
                    else:
                        if cls not in buckets:
                            buckets[cls] = resources.enter_context(SpooledTemporaryFile(max_size=spill))
                        buckets[cls].write(cp.encode("utf-32-le"))
            if not raw:
                break
        boundary("")


def conformance(path):
    rows = checks = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.partition("#")[0].strip()
        if not text or text.startswith("@"):
            continue
        columns = ["".join(chr(int(v, 16)) for v in col.split())
                   for col in text.split(";")[:5]]
        for i, original in enumerate(columns):
            expected = columns[1 if i < 3 else 3]
            output = BytesIO()
            normalize(BytesIO(original.encode()), output, chunk=1, spill=8)
            if output.getvalue() != expected.encode():
                raise ValueError(f"conformance failure at data row {rows + 1}, column {i + 1}")
            checks += 1
        rows += 1
    if not rows:
        raise ValueError("no test cases")
    print(f"UCD {ud.unidata_version}: {rows} rows, {checks} chunked NFC checks passed")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--chunk", type=int, default=65536)
    p.add_argument("--spill", type=int, default=4096, help="RAM threshold per active combining class")
    p.add_argument("--conformance", type=Path, help="NormalizationTest.txt matching Python's UCD")
    args = p.parse_args()
    if args.conformance:
        conformance(args.conformance)
    else:
        normalize(sys.stdin.buffer, sys.stdout.buffer, args.chunk, args.spill)


if __name__ == "__main__":
    main()
