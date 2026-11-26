# Spill NFC

Normalize a UTF-8 stream to Unicode NFC even when its combining sequence exceeds available RAM. The implementation uses Python's standard library. It accepts arbitrary input chunk boundaries, including cuts inside a multibyte character. This is useful for ingestion and archival pipelines where input records have no reliable maximum length.

## Run it

~~~sh
python stream_nfc.py --chunk 1024 --spill 256 < input.txt > normalized.txt
python -c "import unicodedata as u; print(u.unidata_version)"
python stream_nfc.py --conformance NormalizationTest.txt
~~~

The spill limit is per spool, in bytes. Input decoding is strict. If a later byte is malformed, a valid normalized prefix may already have been written. For atomic file replacement, write to a temporary output and rename it only after success.

## How pending output works

A chunk boundary cannot end a combining sequence. Even a long run of marks can be followed by a mark whose canonical combining class requires it to move ahead of the whole run. Decompose incoming characters, group pending marks by combining class, and preserve their input order within each class. Replay buckets in increasing class order, applying canonical composition and blocking. Preserve the starter across eligible zero-class compositions, including Hangul. A second spool delays the surviving suffix until the final starter can be emitted.

Pending text RAM is bounded by the input chunk, the finite number of combining classes, the per-spool threshold, fixed I/O buffers and the bounded composition cache. A single sequence can use temporary disk proportional to its length and can delay output until the sequence ends. Leave sufficient temporary disk space when handling very long sequences.

## Validation

Using Python's Unicode 15.0.0 database, the conformance runner passed all 19,074 rows of the official suite and checked the five NFC identities per row, for 95,370 comparisons. The run used one-byte input chunks and eight-byte spool thresholds. A separate stress case with 400,000 alternating U+0315 and U+0300 marks between a starter and a trailing Z was checked for full reordering and starter composition. These results cover that Unicode version. For a different Python build, use the test data matching its Unicode database.

[Unicode normalization specification](https://www.unicode.org/reports/tr15/) · [Unicode 15.0.0 conformance data](https://www.unicode.org/Public/15.0.0/ucd/NormalizationTest.txt)
