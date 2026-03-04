# Form-Filling Bot (PDF + LLM)

Hello, this is a demo project that automates answering a multi-question web form. The form page contains a Flash-style viewer with a Print PDF button buried in nested iframes, plus answer inputs and a submit button. The bot downloads the PDF, OCRs it, and uses an LLM to answer each question.

Our system runs these steps:

1. **Open** the target URL in Chrome (SeleniumBase CDP mode)
2. **Cloudflare** — skip the challenge if present (up to 5 attempts)
3. **Print PDF** — traverse the iframe tree inside `<main>`, find the "Print PDF" button, click it via CDP mouse events → PDF auto-downloads
4. **OCR** — wait for the PDF in the download dir, then extract text via pdf2image + pytesseract
5. **Answer** — for each question: grab the question text, ask the LLM, fill the form field (text or select)
6. **Submit** — click the submit button

Bonus: `$ make launch-chrome` launches Chrome with PDF auto-download prefs. Close all Chrome windows first, then run it. This lets the Print PDF click trigger a direct download (no popup, no ESC flow).

# STACK

We use **uv** with Python 3.11. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) on your system, then:

```bash
$ make deps
$ make build
$ make check
```

Copy `.env.example` to `.env` and add your `OPENAI_API_KEY`. You also need:

- **Google Chrome**
- **Poppler** (for pdf2image): `brew install poppler` (macOS) or `sudo apt-get install poppler-utils` (Ubuntu)
- **Tesseract** (for OCR): `brew install tesseract` (macOS) or `sudo apt-get install tesseract-ocr` (Ubuntu)

Then you're set.

# USAGE

```bash
# Run the full bot (headless)
$ make bot URL=https://example.com/form
```

## Flow tests (stepwise debugging)

If something breaks mid-pipeline, you can run individual flows:

- `$ make flow-1 URL=<url>` — Open URL and pass Cloudflare (fresh Chrome)
- `$ make flow-1-attach URL=<url>` — Same but connect to an already-open Chrome
- `$ make flow-2` / `flow-2-attach` — Print PDF via iframe (attach = already past Cloudflare)
- `$ make flow-3` / `flow-3-attach` — Fill form and submit (attach = use `tests/exampl-pdf.pdf` instead of live download)

Outputs (screenshots, OCR artifacts) go to `outputs/<run_id>/`. Run ID is printed at start.

## Tests

```bash
$ make test
```

Runs OCR and template-matching tests (image fixtures, no browser). Browser flows: `make flow-1`, `flow-2`, `flow-3`.

# DESIGN

## Print PDF via iframe traversal

The form page embeds a Flash-style viewer with a Print PDF button deep inside nested iframes. Rather than hardcoding selectors, we traverse the iframe tree from `<main>` and search for a button whose text matches "Print PDF". Clicking is done via CDP mouse events for reliability across frame boundaries.

## PDF auto-download

Chrome must have `plugins.always_open_pdf_externally` so clicking Print PDF triggers a direct download instead of opening in-browser. Use `make launch-chrome` to start Chrome with those prefs. Then the bot or flow tests can connect and run.

## Single-shot, no state

The bot runs once and exits. No database, no caching. Temp download dir is per run (under `outputs/<run_id>/download`). The `SB` context manager cleans up the browser when done.
