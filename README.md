# Selenium PDF Question-Answering Bot

A CLI tool that automates answering form questions by downloading a PDF, extracting its text via OCR, and querying an LLM for the answer.

## Prerequisites

- **Python 3.11+**
- **uv** -- [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Google Chrome** installed
- **Poppler** (required by `pdf2image`):
  ```bash
  # macOS
  brew install poppler

  # Ubuntu/Debian
  sudo apt-get install poppler-utils
  ```
- **Tesseract OCR** (required by `pytesseract`):
  ```bash
  # macOS
  brew install tesseract

  # Ubuntu/Debian
  sudo apt-get install tesseract-ocr
  ```

## Setup

```bash
# Clone and enter the project
cd case2

# Install dependencies
uv sync

# Configure your OpenAI API key
cp .env.example .env
# Edit .env and add your key
```

## Usage

```bash
# Basic usage (visible browser)
uv run bot --url "https://example.com/form"

# Headless mode
uv run bot --url "https://example.com/form" --headless

# Custom model and download directory
uv run bot --url "https://example.com/form" --model gpt-4o --download-dir ./downloads

# Override CSS selectors when auto-detection doesn't work
uv run bot --url "https://example.com/form" \
  --question-selector "label.question" \
  --download-selector "a.pdf-link" \
  --input-selector "textarea#answer" \
  --submit-selector "button#submit-btn"
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | *(required)* | URL of the form page |
| `--headless` | off | Run Chrome without a visible window |
| `--download-dir` | temp dir | Directory for downloaded PDFs |
| `--model` | `gpt-4o-mini` | OpenAI model to use |
| `--download-timeout` | `30` | Seconds to wait for PDF download |
| `--question-selector` | auto-detect | CSS selector for the question element |
| `--download-selector` | auto-detect | CSS selector for the download button |
| `--input-selector` | auto-detect | CSS selector for the answer input |
| `--submit-selector` | auto-detect | CSS selector for the submit button |

## How It Works

1. Opens the target URL in Chrome via Selenium
2. Locates and extracts the question text from the page
3. Finds and clicks the PDF download button
4. Waits for the PDF to finish downloading
5. Converts each PDF page to an image (`pdf2image`) and runs OCR (`pytesseract`)
6. Sends the question and extracted text to OpenAI and receives an answer
7. Types the answer into the form input and clicks submit
