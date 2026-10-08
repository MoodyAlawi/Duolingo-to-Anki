# Tutorial

A slow, click-by-click walkthrough. If you just want the commands, read the
[README](../README.md) instead.

By the end you will have an `anki_german_vocabulary.csv` file that imports into
Anki as German → English flashcards.

- [1. Check Python](#1-check-python)
- [2. Export your words from Duolingo (main method)](#2-export-your-words-from-duolingo-main-method)
- [3. Convert for Anki](#3-convert-for-anki)
- [4. Import into Anki](#4-import-into-anki)
- [5. Fallback: extract from a HAR file](#5-fallback-extract-from-a-har-file)
- [6. Read the diagnostic report](#6-read-the-diagnostic-report)
- [7. Troubleshooting](#7-troubleshooting)
- [8. Privacy checklist](#8-privacy-checklist)

## 1. Check Python

Open a terminal in this project folder.

- **Windows:** open the folder in File Explorer, type `powershell` in the address bar, press Enter.
- **macOS / Linux:** open Terminal and `cd` into the folder.

Check your version:

```bash
python --version
```

You need **3.10 or newer**. If the command is not found, try `python3 --version`.
If neither works, install Python from <https://www.python.org/downloads/>.

Nothing else needs installing. There are no extra packages.

> If `python` opens the Microsoft Store on Windows, turn off the app aliases in
> *Settings → Apps → Advanced app settings → App execution aliases*, or just use
> `python3` instead.

## 2. Export your words from Duolingo (main method)

Use the browser script. It asks Duolingo for your whole word list and downloads it as
a CSV. A HAR recording is only the fallback, and it usually misses most words, because
it contains just the pages your browser happened to load.

1. Log in at <https://www.duolingo.com> and open `/practice-hub/words` once.
2. Press `F12`, open the **Console** tab.
   - Chrome blocks pasting the first time. Type `allow pasting` and press Enter.
3. Open `duolingo_export_all.js`, copy everything, paste it into the console, press Enter.
4. A small progress box appears in the top-right corner. Wait roughly 30–90 seconds.
5. Two files download: `duolingo_words_full.csv` and `duolingo_words_full.json`.

If nothing happens, see [step 7](#7-troubleshooting). If the script does not work for you
at all, use the HAR fallback in [step 5](#5-fallback-extract-from-a-har-file).

## 3. Convert for Anki

```bash
python convert_to_anki.py
```

It finds your export automatically — either `duolingo_words_full.csv` (from the browser
script) or `duolingo_words.csv` (from the HAR fallback). You can also be explicit:

```bash
python convert_to_anki.py --input duolingo_words_full.csv
```

Two files are created:

| File | Columns | Use |
| --- | --- | --- |
| `anki_german_vocabulary.csv` | `German`, `English`, `Notes` | Full version |
| `anki_german_vocabulary_basic.csv` | `German`, `English` | Minimal version |

Both are saved as UTF-8, so umlauts (`ä ö ü`) and `ß` are preserved.

## 4. Import into Anki

1. Open Anki.
2. **Tools → Manage Note Types → Add** to create a note type with three fields:
   `German`, `English`, `Notes`. (Or reuse an existing one.)
3. **File → Import** and select `anki_german_vocabulary.csv`.
4. In the import dialog:
   - **Note type:** your German note type
   - **Field separator:** `Comma`
   - **Allow HTML in fields:** off
   - **First line is field names:** on (the file has a header row)
5. Map the columns: `German` → German, `English` → English, `Notes` → Notes.
6. Click **Import**.

You can now review the deck. Because there is no audio and no grammar data, the
cards are simple word → translation cards.

## 5. Fallback: extract from a HAR file

Use this only if the browser script in [step 2](#2-export-your-words-from-duolingo-main-method)
does not work for you. A HAR file is a recording of the network requests your browser made.

> **Warning:** a HAR file contains your login cookies. Never share it, and never
> upload it to GitHub.

1. Log in at <https://www.duolingo.com>.
2. Open your word list: <https://www.duolingo.com/practice-hub/words>
3. Press `F12` to open the developer tools. Open the **Network** tab.
4. Tick **Preserve log** so the list is not cleared on reload.
5. Reload the page, then **scroll slowly all the way down** your word list.
   Duolingo loads words in batches of 50 as you scroll, and only the batches you
   actually load end up in the recording.
6. Save the recording:
   - **Firefox:** right-click any row → *Save all as HAR*
   - **Chrome / Edge:** click the download arrow in the Network toolbar → *Export HAR (with sensitive data)*
7. Move the downloaded `.har` file into this project folder.

Then run the extractor:

```bash
python extract_duolingo.py --har my-download.har
```

If there is exactly one `.har` file in the folder, you can drop the flag:

```bash
python extract_duolingo.py
```

You should see something like:

```
extracted_rows = 251
duplicates_removed = 107
records_without_translation = 0
problems = 0
--- first 10 CSV rows ---
Dokumentarfilm | documentary |  | https://www.duolingo.com/2017-06-30/users/{user_id}/...
```

Three files are created:

| File | What it is |
| --- | --- |
| `duolingo_words.csv` | Your German words and English translations |
| `duolingo_words.json` | The same data in JSON, if you prefer it |
| `diagnostic_report.txt` | A plain-English summary of what was found |

Now go back to [step 3](#3-convert-for-anki) to convert the result.

## 6. Read the diagnostic report

This report is produced by the HAR fallback. If you used the browser script, you can
skip this section.

Open `diagnostic_report.txt` in any text editor. The important section is near the middle:

```
=== COVERAGE / COMPLETENESS WARNING ===
account vocabulary total reported by the API : 4982
lexeme records actually present in this HAR : 358
unique words extracted from this HAR        : 251
words NOT captured in this HAR              : 4731
```

This is normal and does **not** mean something went wrong. Duolingo sends your
words 50 at a time, and a HAR file only contains the batches the browser
requested while you were scrolling. If the numbers here are far apart and you
want every word, use the browser script in
[step 2](#2-export-your-words-from-duolingo-main-method) instead.

Other sections of the report:

- **Anchor search** — confirms which responses contained vocabulary.
- **Schema detected** — the exact field names found in the data.
- **Extraction** — a count check: raw records minus duplicates should equal unique words.
- **Privacy** — confirms account ids were masked.

## 7. Troubleshooting

**`ERROR: no --har given ...`**
Pass the file explicitly: `python extract_duolingo.py --har my-download.har`.
The auto-detect only works when exactly one `.har` file is present.

**`extracted_rows = 0`**
The HAR has no vocabulary responses in it. This usually means you saved the file
before scrolling the word list. Redo the recording in [step 5](#5-fallback-extract-from-a-har-file)
and scroll through the whole list while recording, or use the browser script in
[step 2](#2-export-your-words-from-duolingo-main-method).

**Wrong or missing words, but no error**
Check the coverage warning in `diagnostic_report.txt`. A HAR file is almost
always incomplete, so prefer the browser script.

**Umlauts look like `Ã¤` or `Strasse`**
You are reading the file with the wrong encoding. Open it as UTF-8. In Excel:
*Data → From Text/CSV* and choose **UTF-8** as the file origin.

**Anki shows the header row as a card**
In the import dialog, make sure **First line is field names** is ticked.

**Anki puts everything in one column**
Set the field separator to `Comma` and check that the columns are mapped.

**The `Notes` column is empty**
That is expected. Duolingo's data contains no article, plural or gender
information, and this project does not invent any. You can fill it in yourself
in Anki later.

**The console script does nothing**
Chrome requires you to type `allow pasting` into the console once before it
accepts pasted code. You should also see a progress box in the top-right corner;
if you do not, the script is not running.

## 8. Privacy checklist

Before you push this project to GitHub:

- [ ] `git status` lists no `.har` files.
- [ ] `git status` lists no personal `.csv` or `.json` files.
- [ ] The `.gitignore` in this repo is present and unmodified.
- [ ] You have not pasted your HAR contents into any chat, issue or website.
- [ ] `examples/` only contains the sanitized sample, which has no cookies and a fake account id.

If a HAR file ever does get committed, deleting the file is not enough — the
contents stay in the git history. Treat your session cookies as compromised and
log out of Duolingo, then remove the file from history.
