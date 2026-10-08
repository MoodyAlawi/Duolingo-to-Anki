# Duolingo Vocabulary → Anki

Export your Duolingo word list and turn it into an Anki-ready deck.

- `duolingo_export_all.js` — the main method. Runs in your browser and downloads your complete word list.
- `convert_to_anki.py` — turns that CSV into a clean file you can import into Anki.
- `extract_duolingo.py` — fallback. Pulls words out of a HAR file if you cannot run the browser script.

Everything stays on your computer. The Python scripts run fully offline. The browser
script talks only to Duolingo itself, using the session you are already logged in with.

## Quick start

1. Log in at <https://www.duolingo.com> and open your Words page:
   <https://www.duolingo.com/practice-hub/words>
2. Press `F12` to open DevTools, then open the **Console** tab.
   Chrome blocks pasted code the first time — type `allow pasting` and press Enter.
3. Open `duolingo_export_all.js`, copy all of it, paste it into the Console, press Enter.
4. A progress box appears in the top-right corner. Wait about 30–90 seconds.
   Two files download: `duolingo_words_full.csv` and `duolingo_words_full.json`.
5. Convert it for Anki:

   ```bash
   python convert_to_anki.py
   ```

6. Import `anki_german_vocabulary.csv` into Anki.

If the browser script does not work for you, there is a HAR fallback in
[Fallback: extract from a HAR file](#fallback-extract-from-a-har-file).

## What this does

1. You paste `duolingo_export_all.js` into your browser console on duolingo.com. It pages
   through your whole word list and downloads it as a CSV.
2. `convert_to_anki.py` reformats that CSV into two files built for Anki's importer.

If the browser script does not work for you, `extract_duolingo.py` can pull words out of a
HAR recording instead. That is the fallback, and a HAR file usually contains only part of
your vocabulary.

## Requirements

- Python 3.10 or newer
- No third-party packages — standard library only

## Install

```bash
git clone https://github.com/MoodyAlawi/Duolingo-to-Anki
cd <Duolingo-to-Anki>
```

Optionally use a virtual environment:

```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

There is nothing to install. `requirements.txt` exists only to document that fact.

## Convert for Anki

```bash
python convert_to_anki.py
```

It finds your export automatically — either `duolingo_words_full.csv` (from the browser
script) or `duolingo_words.csv` (from the HAR fallback). You can also point it at a file:

```bash
python convert_to_anki.py --input words.csv
python convert_to_anki.py --help
```

**Outputs**

| File | Columns |
| --- | --- |
| `anki_german_vocabulary.csv` | `German`, `English`, `Notes` |
| `anki_german_vocabulary_basic.csv` | `German`, `English` |

In the `English` column, multiple translations are separated by semicolons, for example
`house; home; residence`.

## Import into Anki

1. Open Anki and choose **File → Import**.
2. Select `anki_german_vocabulary.csv`.
3. Set **Field separator** to `Comma`.
4. Make sure **Allow HTML in fields** is off.
5. Map the columns: field 1 → `German`, field 2 → `English`, field 3 → `Notes`.
6. Import.

Create a note type with those three fields first, or map onto an existing one.

## Fallback: extract from a HAR file

Use this only if the browser script does not work for you. A HAR file is a recording of your
browser's network requests, and it usually contains only a small part of your vocabulary,
because Duolingo loads words 50 at a time and only the pages you actually loaded are recorded.

1. Open <https://www.duolingo.com> and log in.
2. Go to your Words page: `/practice-hub/words`.
3. Press `F12` to open DevTools, then open the **Network** tab.
4. Turn on **Preserve log** so requests are not cleared when the page reloads.
5. Scroll slowly through your whole word list.
6. Save the file:
   - **Firefox:** right-click a request → *Save all as HAR*
   - **Chrome / Edge:** click the download arrow in the Network toolbar → *Export HAR (with sensitive data)*
7. Save it next to these scripts.

Then run the extractor:

```bash
python extract_duolingo.py --har my-download.har
```

If exactly one `.har` file is in the folder, you can leave the flag out:

```bash
python extract_duolingo.py
```

Useful options:

```bash
python extract_duolingo.py --har my-download.har --csv words.csv --report report.txt
python extract_duolingo.py --help
```

**Outputs**

| File | What it is |
| --- | --- |
| `duolingo_words.csv` | The extracted vocabulary |
| `duolingo_words.json` | The same data as JSON |
| `diagnostic_report.txt` | What was found, plus a coverage warning |

Then convert it for Anki as described above.

## Safety / privacy

A HAR file contains your session cookies and account details. Treat it like a password.

- **Never commit or upload a HAR file**, and never attach one to a GitHub issue.
- The included `.gitignore` blocks `*.har`, `*.csv` and `*.json`, so personal files are
  not pushed by accident. Run `git status` before your first push and check nothing
  personal is listed.
- The scripts never print, save or transmit cookies, tokens, headers or your account id.
  Account ids in the output are replaced with `{user_id}`.
- The Python scripts make no network requests at all. The browser script requests data only
  from Duolingo itself — nothing is sent to any other server.

## Limitations

- **The browser script is the main method; the HAR extractor is a fallback.** A HAR file is
  usually incomplete, because Duolingo loads your words 50 at a time and only the pages your
  browser requested are recorded. `diagnostic_report.txt` reports how many words the API says
  you have versus how many were captured.
- **`Notes` is always empty.** Duolingo's response contains no article, plural, gender or
  part-of-speech information, and this project does not invent any.
- **Translations include inflected forms**, such as `(to) run` or `(we/they) run`. These
  come from Duolingo unchanged.
- **Undocumented API.** If Duolingo changes its responses, the scripts may need updating.
- German → English by default. Other languages work if you adjust the URL segments.

## How the export works

`duolingo_export_all.js` asks Duolingo for your word list one page at a time, then downloads
everything it received as a CSV. It runs in your own browser using your existing logged-in
session. It never displays or stores your token.

See [docs/tutorial.md](docs/tutorial.md) for the slower walkthrough.

## Example files

`examples/` contains a sanitized HAR with a few harmless words, plus the files it produces.
You can try both tools without touching real data. The sample is a HAR file, so this uses the
fallback path:

```bash
python extract_duolingo.py --har examples/sample_har.har
python convert_to_anki.py --input duolingo_words.csv
```

## Project layout

```
duolingo_export_all.js   main method: export the full list from your browser
convert_to_anki.py       CSV -> Anki import files
extract_duolingo.py      fallback: HAR -> CSV / JSON / diagnostic report
docs/tutorial.md         step-by-step beginner walkthrough
examples/                sanitized sample data
```

## License

MIT — see [LICENSE](LICENSE).
