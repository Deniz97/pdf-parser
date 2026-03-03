.PHONY: deps build format typecheck bot test launch-chrome flow-1 flow-2 flow-3 flow-1-attach flow-2-attach flow-3-attach

# Install dependencies
deps:
	uv sync

# Build the package
build:
	uv build

# Format code with ruff and black
format:
	uv run ruff format .
	uv run black .

# Type check with mypy
typecheck:
	uv run mypy src/

URL=https://staging.squadhealth.ai/interview
# Run the bot with a URL
bot:
	@if [ -z "$(URL)" ]; then \
		echo "Error: URL is required. Usage: make bot URL=https://example.com"; \
		exit 1; \
	fi
	uv run bot --url $(URL)

# Launch Chrome with PDF auto-download prefs (close all Chrome windows first)
launch-chrome:
	uv run python scripts/launch_chrome.py

# Flow 1: Open URL, pass Cloudflare (run = fresh Chrome; attach = connect to existing)
flow-1:
	uv run python tests/flow_1_cloudflare.py --url $(URL)
flow-1-attach:
	uv run python tests/flow_1_cloudflare.py --url $(URL) --attach

# Flow 2: Print PDF via iframe (run = from start; attach = already past Cloudflare)
flow-2:
	uv run python tests/flow_2_print_pdf.py --url $(URL)
flow-2-attach:
	uv run python tests/flow_2_print_pdf.py --url $(URL) --attach

# Flow 3: Fill form and submit (run = full bot; attach = use exampl-pdf.pdf)
flow-3:
	uv run python tests/flow_3_form_submit.py --url $(URL)
flow-3-attach:
	uv run python tests/flow_3_form_submit.py --url $(URL) --attach

# Run tests (use -m "not cloudflare" to skip live browser tests)
test:
	uv run pytest tests/
