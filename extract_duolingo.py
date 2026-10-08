"""Extract German->English vocabulary from a local Duolingo HAR archive.

Fully offline: reads the HAR, writes CSV/JSON/report. No network access.
Secrets (cookies, auth headers, tokens) and account identifiers are never
read into the output; URL paths are redacted before being written.

Usage:
    python extract_duolingo.py --har my-download.har
    python extract_duolingo.py --har my-download.har --csv words.csv
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_CSV = Path("duolingo_words.csv")
DEFAULT_JSON = Path("duolingo_words.json")
DEFAULT_REPORT = Path("diagnostic_report.txt")

# A common German word used only to help spot vocabulary responses.
# Extraction does not depend on it.
DEFAULT_ANCHOR = "Dokumentarfilm"

# Schema discovered by probing the HAR (do not assume more than this exists).
LEXEME_LIST_KEYS = ("learnedLexemes", "practiceLexemes")
TEXT_KEYS = ("text", "word", "learning_word", "normal_form", "surface_form")
TRANSLATION_KEYS = ("translations", "translation", "meanings", "glosses")

# Grammar metadata keys we would carry into Notes if a response ever had them.
GRAMMAR_KEYS = (
    "article", "gender", "plural", "pos", "partOfSpeech",
    "grammar", "inflection", "wordType", "lexemeType",
)

PAGINATION_URL = re.compile(r"/users/[^/]+/")


def redact_url(url: str) -> str:
    """Keep scheme/host/path; drop query+fragment and mask the account id."""
    try:
        parts = urlsplit(url)
    except Exception:
        return "<unparsable-url>"
    path = PAGINATION_URL.sub("/users/{user_id}/", parts.path)
    return f"{parts.scheme}://{parts.netloc}{path}"


def content_bytes(entry: dict) -> bytes:
    content = (entry.get("response") or {}).get("content") or {}
    text = content.get("text")
    if text is None:
        return b""
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text, validate=False)
        except Exception:
            return b""
    return text.encode("utf-8", "replace")


def tolerant_entries(raw_text: str):
    """Fallback for malformed HAR: bracket-match the entries array."""
    start = raw_text.find('"entries"')
    if start < 0:
        return []
    start = raw_text.find("[", start)
    if start < 0:
        return []
    dec = json.JSONDecoder()
    i, n = start + 1, len(raw_text)
    out = []
    while i < n:
        while i < n and raw_text[i] in " \r\n\t,":
            i += 1
        if i >= n or raw_text[i] == "]":
            break
        try:
            obj, end = dec.raw_decode(raw_text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        out.append(obj)
        i = end
    return out


def load_entries(path: Path):
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(raw_text)["log"]["entries"], "json.load", []
    except Exception as exc:
        first_error = f"{type(exc).__name__}: {exc}"
    entries = tolerant_entries(raw_text)
    return entries, "tolerant_bracket_scanner", [first_error]


def maybe_decode_nested(value):
    """Recursively decode JSON that is escaped inside strings."""
    if isinstance(value, str):
        s = value.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                return maybe_decode_nested(json.loads(s))
            except Exception:
                return value
        return value
    if isinstance(value, dict):
        return {k: maybe_decode_nested(v) for k, v in value.items()}
    if isinstance(value, list):
        return [maybe_decode_nested(v) for v in value]
    return value


def find_lexeme_containers(node, depth=0):
    """Return the raw lexeme lists found anywhere in a payload."""
    buckets = []
    if depth > 16:
        return buckets
    if isinstance(node, dict):
        for key in LEXEME_LIST_KEYS:
            bucket = node.get(key)
            if isinstance(bucket, list):
                buckets.append(bucket)
        for v in node.values():
            buckets.extend(find_lexeme_containers(v, depth + 1))
    elif isinstance(node, list):
        for v in node[:5000]:
            buckets.extend(find_lexeme_containers(v, depth + 1))
    return buckets


def collect_vocab_shape(node, out, depth=0):
    """Fallback: dicts carrying a word-like key plus translation-like key."""
    if depth > 16:
        return
    if isinstance(node, dict):
        low = {k.lower(): k for k in node}
        text_key = next((low[k] for k in TEXT_KEYS if k in low), None)
        trans_key = next((low[k] for k in TRANSLATION_KEYS if k in low), None)
        if text_key and trans_key:
            out.append(node)
        for v in node.values():
            collect_vocab_shape(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node[:5000]:
            collect_vocab_shape(v, out, depth + 1)


def looks_like_vocab(rec: dict) -> bool:
    german = pick(rec, TEXT_KEYS)
    if not isinstance(german, str):
        return False
    german = german.strip()
    if not german or len(german) > 120 or "\n" in german:
        return False
    return bool(normalize_translations(pick(rec, TRANSLATION_KEYS)))


def normalize_translations(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if isinstance(value, dict):
        value = list(value.values())
    out = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str):
            s = item.strip()
        elif isinstance(item, dict):
            s = str(
                item.get("translation") or item.get("text") or item.get("meaning") or ""
            ).strip()
        else:
            s = str(item).strip()
        if s:
            out.append(s)
    return out


def pick(record: dict, keys):
    low = {k.lower(): k for k in record}
    for key in keys:
        if key in low:
            return record[low[key]]
    return None


def find_default_har() -> Path | None:
    """Return the only *.har file in the current folder, if there is exactly one."""
    candidates = sorted(p for p in Path.cwd().iterdir() if p.suffix.lower() == ".har")
    return candidates[0] if len(candidates) == 1 else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract German vocabulary from a local Duolingo HAR file.",
        epilog=(
            "Everything runs offline. Your HAR is only read, never modified or uploaded.\n"
            "See docs/tutorial.md for step-by-step instructions."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--har", type=Path, default=None,
        help="Path to the .har file (default: the only *.har in this folder).",
    )
    parser.add_argument(
        "--csv", type=Path, default=DEFAULT_CSV,
        help=f"Output CSV path (default: {DEFAULT_CSV}).",
    )
    parser.add_argument(
        "--json", type=Path, default=DEFAULT_JSON,
        help=f"Output JSON path (default: {DEFAULT_JSON}).",
    )
    parser.add_argument(
        "--report", type=Path, default=DEFAULT_REPORT,
        help=f"Diagnostic report path (default: {DEFAULT_REPORT}).",
    )
    parser.add_argument(
        "--anchor", default=DEFAULT_ANCHOR,
        help=f"Diagnostic German word used to spot vocabulary responses (default: {DEFAULT_ANCHOR}).",
    )
    args = parser.parse_args(argv)

    har_path: Path = args.har
    if har_path is None:
        found = find_default_har()
        if found is None:
            print("ERROR: no --har given and the current folder does not contain exactly one *.har file.")
            print("Example:  python extract_duolingo.py --har my-download.har")
            return 2
        har_path = found
        print(f"Using HAR file: {har_path.name}")

    csv_path: Path = args.csv
    json_path: Path = args.json
    report_path: Path = args.report
    anchor: str = args.anchor

    report: list[str] = []
    problems: list[str] = []

    if not har_path.exists():
        print(f"ERROR: HAR not found: {har_path}")
        return 1

    entries, parser_used, parse_notes = load_entries(har_path)
    report.append(f"HAR file        : {har_path.name}")
    report.append(f"HAR size bytes  : {har_path.stat().st_size}")
    report.append(f"parser used     : {parser_used}")
    report.append(f"HAR entries     : {len(entries)}")
    for note in parse_notes:
        report.append(f"primary parser  : {note}")
        problems.append(f"Primary json.load failed ({note}); used tolerant scanner.")

    anchor_urls: list[str] = []
    vocab_sources: list[str] = []
    coverage_pages: list[str] = []
    declared_total = None
    schema_fields: set[str] = set()
    raw_records: list[tuple[str, dict]] = []
    decode_failures: list[str] = []
    per_entry_counts: list[str] = []

    for idx, entry in enumerate(entries):
        raw = content_bytes(entry)
        if not raw:
            continue
        text = raw.decode("utf-8", "replace")
        url = (entry.get("request") or {}).get("url", "")
        safe = redact_url(url)

        if anchor in text:
            anchor_urls.append(f"  entry[{idx}] {len(raw)}B {safe}")

        if safe.endswith("/learned-lexemes/count"):
            try:
                declared_total = json.loads(text).get("lexemeCount", declared_total)
            except Exception:
                pass
            continue

        # Selection is structural: any response whose JSON carries lexeme lists.
        # The anchor is only used to confirm which endpoint family is relevant.
        if '"learnedLexemes"' not in text and '"practiceLexemes"' not in text:
            continue

        try:
            payload = json.loads(text)
        except Exception as exc:
            if anchor in text:
                decode_failures.append(f"  entry[{idx}] json.load failed: {type(exc).__name__}")
                problems.append(f"entry[{idx}] response body is not plain JSON: {type(exc).__name__}")
            continue

        payload = maybe_decode_nested(payload)
        pag = payload.get("pagination") if isinstance(payload, dict) else None
        if isinstance(pag, dict):
            start = pag.get("previousStartIndex")
            if start is None:
                start = 0
            total = pag.get("totalLexemes")
            if isinstance(total, int):
                declared_total = total
            coverage_pages.append(
                f"  entry[{idx}] records {start}..{pag.get('nextStartIndex')} "
                f"(pageSize={pag.get('pageSize')}, totalDeclared={total})"
            )
        buckets = find_lexeme_containers(payload)
        records: list[dict] = []
        for bucket in buckets:
            records.extend(r for r in bucket if isinstance(r, dict))
        if not records:
            found: list[dict] = []
            collect_vocab_shape(payload, found)
            records = found

        records = [r for r in records if looks_like_vocab(r)]
        if not records:
            continue
        vocab_sources.append(f"  entry[{idx}] {len(raw)}B records={len(records)} {safe}")
        per_entry_counts.append(f"  entry[{idx}] {len(records)}")
        for rec in records:
            schema_fields.update(rec.keys())
        raw_records.extend((safe, rec) for rec in records)

    report.append("")
    report.append("=== Anchor search ('%s') ===" % anchor)
    report.append(f"response bodies containing anchor : {len(anchor_urls)}")
    report.extend(anchor_urls)
    report.append("")
    report.append("=== Vocabulary-bearing responses (structural match) ===")
    report.append(f"count : {len(vocab_sources)}")
    report.extend(vocab_sources)
    report.append("")
    report.append("=== Decode problems ===")
    report.extend(decode_failures or ["  none"])

    report.append("")
    report.append("=== Schema detected ===")
    report.append(f"record field names observed : {sorted(schema_fields)}")
    report.append(f"german text field           : {[k for k in TEXT_KEYS if k in schema_fields]}")
    report.append(f"translation field           : {[k for k in TRANSLATION_KEYS if k in schema_fields]}")
    grammar_present = sorted(k for k in schema_fields if k.lower() in {g.lower() for g in GRAMMAR_KEYS})
    report.append(f"grammar/article/plural fields present : {grammar_present or 'NONE'}")
    if not grammar_present:
        report.append(
            "  -> The learned-lexemes payload carries no article, gender, plural or "
            "part-of-speech data; Notes is therefore left empty for those records."
        )
    # Fields deliberately not turned into columns.
    exported = {k.lower() for k in TEXT_KEYS} | {k.lower() for k in TRANSLATION_KEYS}
    other = sorted(k for k in schema_fields if k.lower() not in exported)
    report.append(f"other fields present (not exported)   : {other}")

    merged: "OrderedDict[str, dict]" = OrderedDict()
    raw_count = 0
    duplicates_removed = 0
    missing_translation: list[str] = []

    for source_url, rec in raw_records:
        german = pick(rec, TEXT_KEYS)
        if not isinstance(german, str) or not german.strip():
            continue
        raw_count += 1
        german = german.strip()
        translations = normalize_translations(pick(rec, TRANSLATION_KEYS))
        key = german.casefold()

        if key in merged:
            duplicates_removed += 1
            existing = merged[key]["English"]
            for t in translations:
                if t not in existing:
                    existing.append(t)
            continue
        merged[key] = {
            "German": german,
            "English": translations,
            "Notes": "",
            "Source_URL": source_url,
        }

    rows = []
    for entry_data in merged.values():
        german, translations = entry_data["German"], entry_data["English"]
        if not translations:
            missing_translation.append(german)
        rows.append(
            {
                "German": german,
                "English": ", ".join(translations),
                "Notes": entry_data["Notes"],
                "Source_URL": entry_data["Source_URL"],
            }
        )

    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["German", "English", "Notes", "Source_URL"])
        writer.writeheader()
        writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(
            [
                {
                    "german": r["German"],
                    "english": [t for t in r["English"].split(", ") if t],
                    "notes": r["Notes"],
                    "source_url": r["Source_URL"],
                }
                for r in rows
            ],
            fh,
            ensure_ascii=False,
            indent=2,
        )
        fh.write("\n")

    report.append("")
    report.append("=== Extraction ===")
    report.append(f"raw lexeme records seen      : {raw_count}")
    report.append(f"unique German entries        : {len(rows)}")
    report.append(f"duplicates removed           : {duplicates_removed}")
    if raw_count - duplicates_removed != len(rows):
        problems.append(
            f"Accounting mismatch: raw({raw_count}) - duplicates({duplicates_removed}) "
            f"!= unique({len(rows)})"
        )
    report.append(
        f"accounting check             : {raw_count} - {duplicates_removed} = "
        f"{raw_count - duplicates_removed} ({'OK' if raw_count - duplicates_removed == len(rows) else 'MISMATCH'})"
    )
    report.append(
        "note : duplicates come from the same vocabulary page being captured "
        "repeatedly in the HAR; translations were unioned across duplicates."
    )

    report.append("")
    report.append("=== COVERAGE / COMPLETENESS WARNING ===")
    report.append(f"account vocabulary total reported by the API : {declared_total}")
    report.append(f"lexeme records actually present in this HAR : {raw_count}")
    report.append(f"unique words extracted from this HAR        : {len(rows)}")
    if declared_total:
        report.append(f"words NOT captured in this HAR              : {declared_total - len(rows)}")
        report.append(
            "  -> The learned-lexemes endpoint is paginated (limit=50). This HAR only "
            "contains the pages that happened to be captured while recording."
        )
    report.append("captured learned-lexemes pages (by startIndex):")
    report.extend(sorted(set(coverage_pages)) or ["  none"])
    report.append(
        "  -> The full vocabulary was NOT recorded. To obtain it, re-record the HAR "
        "while paginating through the entire vocabulary list, or request the "
        "endpoint for startIndex 0, 50, 100, ... up to the reported total."
    )

    report.append(f"German keys with no translation : {len(missing_translation)}")
    for g in missing_translation:
        report.append(f"  UNMATCHED: {g}  (English left blank)")
        problems.append(f"No confidence-matched English translation for '{g}'; left blank.")

    umlaut_rows = sum(1 for r in rows if any(c in r["German"] for c in "äöüÄÖÜß"))
    report.append(f"rows containing umlauts/ß : {umlaut_rows}")

    report.append("")
    report.append("=== Outputs ===")
    report.append(f"CSV  : {csv_path} (UTF-8 with BOM for Excel, umlauts preserved)")
    report.append(f"JSON : {json_path} (UTF-8, ensure_ascii=False)")
    report.append("")
    report.append("=== Privacy ===")
    report.append(
        "account id in URLs masked as {user_id}; no credential material, "
        "no request headers and no query strings were exported."
    )

    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"extracted_rows = {len(rows)}")
    print(f"duplicates_removed = {duplicates_removed}")
    print(f"records_without_translation = {len(missing_translation)}")
    print(f"problems = {len(problems)}")
    for p in problems:
        print(f"  - {p}")
    print("--- first 10 CSV rows ---")
    for r in rows[:10]:
        print(f"{r['German']} | {r['English']} | {r['Notes']} | {r['Source_URL']}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
