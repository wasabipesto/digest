set dotenv-load

# List commands, default
default:
  just --list

# Run the full digest
run:
    uv run main.py

# Run the digest with one loader
run-one source:
    uv run main.py --source {{source}}

# Serve the web view
web:
    @if [ ! -f digest_results.json ]; then echo "Results missing! Run the loaders first."; exit 1; fi
    @echo "Starting web server on http://localhost:8000"
    python3 -m http.server -b localhost 8000

# Initialize by installing deps and copying the env file
init:
    uv sync
    @if [ -f .env ]; then echo ".env file already exists!"; exit 1; fi
    cp .env.example .env
    nano .env
