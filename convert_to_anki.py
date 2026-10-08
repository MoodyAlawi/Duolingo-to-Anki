"""Convert the extracted Duolingo vocabulary CSV into Anki-importable CSVs.

Reads : duolingo_words.csv by default (never modified)
Writes: anki_german_vocabulary.csv        (German, English, Notes)
        anki_german_vocabulary_basic.csv  (German, English)

Translation lists are split on ", " -> re-joined with "; ".
No translation or grammatical information is invented: the source carries no
article/plural/gender/verb metadata, so Notes is left empty rather than guessed.

Usage:
    python convert_to_anki.py
    python convert_to_anki.py --input duolingo_words.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

DEFAULT_INPUTS = (Path("duolingo_words.csv"), Path("duolingo_words_full.csv"))
DEFAULT_OUT_FULL = Path("anki_german_vocabulary.csv")
DEFAULT_OUT_BASIC = Path("anki_german_vocabulary_basic.csv")

GERMAN_COL = "German"
ENGLISH_COL = "English"
NOTES_COL = "Notes"


def find_default_input() -> Path | None:
    for candidate in DEFAULT_INPUTS:
        if candidate.exists():
            return candidate
    return None


def read_source(path: Path):
    raw = path.read_bytes()
    had_bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), list(reader.fieldnames or []), had_bom


def split_translations(value: str) -> list[str]:
    """Source joins translations with ', '; recover the individual list."""
    parts = [p.strip() for p in value.split(", ")]
    out: list[str] = []
    for p in parts:
        if p and p not in out:
            out.append(p)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert an extracted Duolingo vocabulary CSV into Anki import files.",
        epilog="See docs/tutorial.md for step-by-step instructions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", type=Path, default=None,
        help="CSV produced by extract_duolingo.py (default: duolingo_words.csv, "
             "or duolingo_words_full.csv if that is what exists).",
    )
    parser.add_argument(
        "--out-full", type=Path, default=DEFAULT_OUT_FULL,
        help=f"German/English/Notes output (default: {DEFAULT_OUT_FULL}).",
    )
    parser.add_argument(
        "--out-basic", type=Path, default=DEFAULT_OUT_BASIC,
        help=f"German/English output (default: {DEFAULT_OUT_BASIC}).",
    )
    args = parser.parse_args(argv)

    source: Path = args.input
    if source is None:
        found = find_default_input()
        if found is None:
            print("ERROR: no --input given and no duolingo_words.csv found in this folder.")
            print("Example:  python convert_to_anki.py --input duolingo_words.csv")
            return 2
        source = found

    out_full: Path = args.out_full
    out_basic: Path = args.out_basic

    if not source.exists():
        print(f"ERROR: input not found: {source}")
        return 1

    rows, columns, had_bom = read_source(source)
    print(f"input_filename = {source}")
    print(f"original_rows  = {len(rows)}")
    print(f"detected_columns = {columns}")
    print(f"input_had_bom  = {had_bom}")
    print(f"german_column  = {GERMAN_COL}")
    print(f"translation_column = {ENGLISH_COL}")

    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    duplicates_removed = 0
    empty_english: list[str] = []
    split_counts: list[int] = []

    for row in rows:
        german = (row.get(GERMAN_COL) or "").strip()
        if not german:
            continue
        translations = split_translations(row.get(ENGLISH_COL) or "")
        split_counts.append(len(translations))
        english = "; ".join(translations)
        if not english:
            empty_english.append(german)

        key = (german, english)
        if key in seen:
            duplicates_removed += 1
            continue
        seen.add(key)
        records.append({GERMAN_COL: german, ENGLISH_COL: english, NOTES_COL: ""})

    print(f"split_into_semicolons = {len(records)}")
    print(f"max_translations_per_row = {max(split_counts) if split_counts else 0}")

    def write(path: Path, fieldnames: list[str]) -> None:
        # UTF-8 without BOM: keeps the header field names clean for Anki's
        # importer (a BOM would make the first column read as "\ufeffGerman").
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=fieldnames, extrasaction="ignore", quoting=csv.QUOTE_MINIMAL
            )
            writer.writeheader()
            writer.writerows(records)

    write(out_full, [GERMAN_COL, ENGLISH_COL, NOTES_COL])
    write(out_basic, [GERMAN_COL, ENGLISH_COL])

    print(f"duplicates_removed = {duplicates_removed}")
    print(f"rows_without_translation = {len(empty_english)}")
    for g in empty_english[:20]:
        print(f"  UNMATCHED: {g}")
    print(f"wrote {out_full} and {out_basic}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
