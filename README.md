# DQS Apps

The team's little apps in one window (repository: QCA, Quality Control Apps). Download `DQSApps.exe` once;
it keeps itself up to date (see "Releases and auto-update"). The window is drawn by Microsoft Edge WebView2, which comes
with Windows 11 and up-to-date Windows 10; if it's missing, the app says where to get it.

| App | What it does |
|---|---|
| **Price Extractor - Europe** | Daily supplier price lists to Excel, in the final files' columns. Most of this document. |
| **Image Editor** | The same edits on many pictures: rotate, mirror, cut to a ratio, resolutions, brightness, contrast, colour, sharpness, format. Originals are never changed. |
| **Fruit Counter** | Marks every fruit on a picture (or every berry, bunch, punnet...); you check and correct the marks. Saves an Excel with the counts and the marked pictures. |
| *Private apps* | Only with the secret key: see "Private apps". |

## Fruit Counter

1. Drop the pictures. Each one is counted when you select it.
2. **Count** says what counts as one:

   | Count | Counts |
   |---|---|
   | Fruit & vegetables | each piece (the default) |
   | Grapes | berries, or bunches |
   | Bananas | fingers, or hands |
   | Tomatoes on the vine | tomatoes, or trusses |
   | Berries in punnets | berries, or punnets |
   | Asparagus, from the cut ends | spears |
   | Cauliflower, broccoli, lettuce | heads |

   Groups (bunches, hands, trusses, punnets) need one of them measured first: the screen asks for it.
3. **Check the marks:** left click adds, right click removes, the wheel zooms, drag moves around, Undo (Ctrl+Z).
4. If it's off, **Measure one** (drag across one, edge to edge): it counts again looking for things of that size
   **and colour**. **Count again** keeps using it. The *fewer / more* slider changes how strict it is.
5. **Save results**: `Fruit counts.xlsx` (count, what was counted, found automatically, added and removed by hand)
   and a copy of each picture with its marks numbered.

It counts with an AI model that outlines things in a picture (MobileSAM, in `models/`, run on the computer's
processor; see `models/README.md`). The model reads the picture once, then is asked "what is here?" at the likely
middles of things and across the picture; outlines alike in size, colour and shape are counted. A group is asked
about with a box of its size, because at one point on touching bunches the model answers "this berry" or "all the
grapes". The counting is in `apps/fruit_model.py` (its settings are at the top). Without the model files the
plain counter in `apps/fruit_count.py` is used.

How well it does (59 example pictures counted by hand; "within 10%" = at most 1 wrong in 10):

| | Within 10% | Exact | Time per picture |
|---|---|---|---|
| Automatic | 49 of 59 | 34 | about 5 s |
| One fruit measured | 50 of 59 | 37 | about 2.5 s |
| Plain counter (before), one fruit measured | 27 of 59 | – | under 1 s |

Hardest: lobed or irregular things counted automatically (peppers by their lobes: measure one), fruit hidden
under others in a full box, and empty tray cells next to a few fruit. Big piles take longer: about 30 s for
350 grapes. The first count after opening the app also loads the model (a few seconds).

### Sharing corrected counts (to make the counter better)

With the **team key** (typed once per PC: "Help improve counting" under Save results), every picture saved with
*Every mark checked* ticked is sent to the team's Google Drive as a lesson: a smaller copy of the picture, what the
counter found and what the person corrected it to, with the count mode and the measured fruit. Lessons wait in
`%APPDATA%\PriceExtractor\lessons` and are sent in the background, so saving never waits on the internet.

- They go to the shared drive "Fruit Counter lessons" through a Google service account that is only a
  **Contributor** there: it can add files and can't delete any. Its key is in `apps/locked/lessons.enc`, encrypted
  with the team key; the key file itself (`dqsapps.json`) is never in the repository.
- `python tools/fruit_lessons.py` downloads the new lessons, to tune the counter on them; the improved settings are
  then published as a normal version.
- New team key or new service account: `python tools/lock_lessons.py <key.json> <shared drive id> [--new-key]`
  (the team key is kept in `private_apps/TEAM_KEY.txt`).

## Private apps

"Unlock more apps" in the sidebar asks for the secret key. Without it these apps can't be used or read, not
even their names: `apps/locked/apps.enc` is encrypted with the key, and the key isn't stored in the program or on
GitHub. Their source and the key are only in `private_apps/` on the maintainer's PC (git ignores that folder), so
**keep a safe copy of it**: they can't be recovered without it.

- Change a private app: edit it in `private_apps/`, run `python tools/lock_apps.py`, commit `apps/locked/apps.enc`
  and publish a version.
- Change the key (e.g. someone leaves): `python tools/lock_apps.py --new-key`, commit, publish a version, and give
  the new key to whoever should keep access.
- A private app is a `.py` file with a class `Api(host)` (what its screen can call) and the strings `HTML` and `JS`
  (its screen; `view`, `app`, `dqs` and `hooks` are available in the JS), listed in `tools/lock_apps.py`. It can only use libraries
  the program already bundles (add others to `hiddenimports` in `DQSApps.spec`).

# Price Extractor - Europe

Reads the daily price lists (pdf, WhatsApp .txt, saved web page .mhtml, Excel, pictures) and writes the prices
in the same columns as the final Excel files on OneDrive, ready to paste.

## Daily use

1. Open DQS Apps and choose **Price Extractor - Europe**.
2. Drop the day's price files anywhere on the window (or a whole folder). The supplier of each file is shown.
3. Click **Extract prices**. The results appear on the right: the Excel files, and tabs for anything to look at.

The output folder gets:

| File | What |
|---|---|
| `Prices DD-MM-YYYY.xlsx` | One tab per supplier whose final file is a single table (Anaco Greeve, Kissao, Timerfruit...) |
| `<Supplier> DD-MM-YYYY.xlsx` | One file per supplier whose final file has **a tab per species** (Verdi, Olympic, Van der Lans, Jaguar, Everest, Fruitfactor, Westfalia). Same tabs and size columns as the final file. |

Yellow header cells are columns or tabs that don't exist in the final file yet (a new size, a new species).

The results also list:
- **Not extracted**: a product the extractor doesn't know. Add it to
  `pricex/data/species.json` (see below) and run again.
- **Not processed**: files whose supplier wasn't recognised, or whose layout changed so much the parser failed.

Command line alternative: `python extract.py "folder or files" -o "output folder"`

## Rules applied to every supplier

- Only rows with a numeric price ("POR", "On request", "exp", dates... are skipped).
- Grouped sizes are split into one row per size: `6/7`, `8-9-10`, `12 & 14`.
  A range follows the species' real sizes (`size_series` in `species.json`): mangoes `6-12` -> 6, 7, 8, 9, 10, 12;
  avocados `10--24` -> 10, 12, ... 24. A range Excel turned into a date (`01/10/2020` = "10-20") is read back as 10 to 20.
  Species without a series only expand `a--b`; `6-8` stays 6 and 8.
  Kept as one size: `Mix 12-16`, mandarin counts like `2-105`.
- `250g +`, `250+gr` become `250+`.
- Several origins are split the same way: `Dom. Rep. / Colombia` -> one row for Dominican Republic and one for
  Colombia (also `CH/COL/GUA`, `Ecua / Col`). Only split when every part is a known country (`origins.json`).
- **Price check**: each price is compared with the other offers of the same product (species, variety, origin,
  weight, box pp, packing; any brand or size). A price 3x above or below the usual one is a typo
  (e.g. Torres' Palmer 6/7 at €76 when the rest is €6-7):
  - if the same size is already offered at a normal price, the wrong row is **dropped**;
  - otherwise it's **kept with the price cell in red**.
  Both appear under "Price checks" in the results. The 3x limit is `OUTLIER` in `pricex/base.py`.
- Rows that are exactly identical are kept only once (the log says how many were removed).
- **Per kg check** (never removes anything, only marks the price red and lists it under "Price checks"):
  - labelled per kg but priced like a box: more than €25/kg, or price x box weight above €150
    (bins labelled per kg are normal and not flagged);
  - priced like a kg without saying so: under €0.15 per kg of box weight, a bin (100 kg or more, or "bin"
    in the text), or under €1 when no weight is given.
  The limits are at the top of `check_per_kg` in `pricex/base.py`. In the per-species files, a group goes into its
  own column if the final file already has one (e.g. Verdi plums `45/50`).
- Pack sizes like `12x100`, `10x500gr` go to DETAIL; the size becomes `N/S`.
- Empty variety becomes the species name. Species are written in plural (`Mangoes`, `Avocados`).
- "By air", "RTE"... go to TYPE (or DETAIL, depending on what that supplier's final file does).
- Origins are written the way each final file does: codes (`RSA`, `BR`) or names (`South Africa`).

## Price lists sent as pictures

Pictures (png, jpg, webp...) are read with OCR, so the extractor works when a supplier sends a screenshot
instead of a pdf (so far: Kissao). The file name doesn't need the supplier: it's recognised from the text.

- Two OCR engines read the picture: RapidOCR (best for names and sizes) and the OCR built into Windows
  (best for numbers). Prices come from Windows' reading; sizes and varieties are compared between the two.
- Misread words are corrected to known words: species, countries, `data/ocr_words.txt`, and every
  variety already typed in the final files (rebuilt by `tools/update_templates.py`).
- **Nothing is guessed.** Rows where the two readings disagree, something is missing, or a variety could
  only be read once are kept but marked red, with the reason in the report. The report also says the file
  came from a picture: compare the rows with it before using them.
- Small pictures read worse. If a supplier can send the pdf or a bigger picture, that's always better.

## When something changes

**A new product** (e.g. "Rambutan" shows up as not extracted): open `pricex/data/species.json` and add it under
`species`, with the words suppliers use for it:

```json
"Rambutans": ["rambutan", "rambutans"],
```

Products you never want go under `ignore`. Labels that belong in the TYPE column instead of the name go under
`type_words` (e.g. `"fairtrade": "FAIRTRADE"`: "Fairtrade Limes" -> Limes with TYPE = FAIRTRADE).
Codes a supplier uses instead of the variety name go under `variety_codes` (e.g. `"329-5": "Gem"`).
Fixed packaging for a species and box weight goes under `packaging_rules`: grapes of 5 kg are
`CARTON 10X500G` when the list says carton or nothing about the packaging; if it mentions another
packaging listed in `unless` (foam, wood, plastic, bags...), the supplier's packaging is kept.
Varieties that identify a species on their own (when a supplier
writes just "Keitt") go under `varieties`.

**A new country spelling**: add it to `pricex/data/origins.json`.

**You added a column or a tab to a final Excel**: copy the final files to a folder and run

```
python tools/update_templates.py "folder with the final files"
```

A final file with more than one tab automatically produces a separate file; one tab means a tab in the combined file.

**How files are recognised**: the file name is not trusted. A file belongs to a supplier when its text contains one of the supplier's `match_text` identifiers (web domain, e-mail, company name, Chamber of Commerce number), or, when there is none (WhatsApp messages), when its layout matches the supplier's `layout_hints` and the supplier's parser reads real products from it. The name only breaks ties (typos are fine). If the name and the content disagree, the content wins and the log says so; files that match no supplier are listed as not recognised. When adding a supplier, give it identifiers and layout hints.

**A supplier changed its layout, or a new supplier**: each supplier is one file in `pricex/suppliers/`
(e.g. `kissao.py`). The top of each file shows what the layout looks like. To add a supplier, copy the one
whose layout is most similar, change `name`, `final_file`, `match_names` (words in the file name) and the
reading part. It's picked up automatically.

Two tools help:

```
python tools/pdf_lines.py "Supplier 27-10-2026.pdf"                      # how the pdf is seen, with positions
python tools/check.py "Supplier 27-10-2026.pdf" "SUPPLIER final.xlsx"    # compare with what's in the final file
python tools/check.py "folder"                                           # check every price file in a folder
```

`check.py` compares sizes and prices against the rows already in the final Excel for the same date, so
after typing a day by hand you can confirm the extractor would have produced the same.

## Releases and auto-update (for the team)

The team uses `DQSApps.exe` from the GitHub Releases page. It checks GitHub every time it opens and,
when there is a newer release, offers to update: it downloads the new exe, replaces itself and restarts.

**Publishing a new version** (after committing and pushing your changes):

```
git tag v2.1.0
git push origin v2.1.0
```

The GitHub Action (`.github/workflows/release.yml`) builds the exe on a Windows machine, checks that it starts
and loads every supplier, and publishes it as release `v2.1.0`. Versions are compared as numbers
(v1.10.0 is newer than v1.9.0); always tag higher than the last release. The Action writes the version and the
repository name into `version.py` itself; you never edit them.

**For the team, once:** download `DQSApps.exe` from the latest release and put it in a folder they can
write to (Desktop, Documents, `C:\Users\<name>\DQSApps`), not in `C:\Program Files`. The first time,
Windows SmartScreen may say "Windows protected your PC": More info -> Run anyway. Updates don't ask again.

Notes:
- The repository must be **public** for the update check to work without passwords.
- `species.json`, `origins.json` and the column templates are inside the exe: to change them for everyone,
  change them in the repository and publish a new version.
- Each release has the same program twice: `DQSApps.exe`, and `PriceExtractor.exe` for apps installed before the
  suite (up to v1.0.7), which only look for that name. Those keep their file name on the user's PC, so shortcuts
  still work. Drop that copy from `release.yml` once everybody is on v2.
- Settings (output folder) are kept in `%APPDATA%\PriceExtractor`, so they survive updates.
- `DQSApps.exe --update` updates without asking; `DQSApps.exe --extract <folder> -o <out>`
  runs without a window and writes `report.txt`.
- Build locally (optional): `pip install -r requirements.txt pyinstaller`, then `pip install --no-deps rapidocr-onnxruntime` and `pyinstaller DQSApps.spec`.

## Files

```
dqs.py                  opens the window and connects the screens to the apps
ui/                     the screens: index.html, style.css, shell.js (sidebar, update card, unlock), one .js per app
apps/                   the work behind each screen: price_extractor, image_editor + image_tools,
                        fruit_counter + fruit_count, locked (private apps), common (settings, files, the Host)
extract.py              command line
pricex/
  suppliers/            one parser per supplier (+ _common.py, _pdf.py helpers)
  data/species.json     species names, aliases, ignored products
  data/origins.json     countries and their codes/spellings
  data/templates.json   columns and tabs of each final file (made by tools/update_templates.py)
  normalize.py          shared rules (prices, sizes, weights, origins)
  output.py             Excel writing
tools/                  check.py, pdf_lines.py, update_templates.py
```

Needs: `pip install -r requirements.txt`, then `pip install --no-deps rapidocr-onnxruntime`
