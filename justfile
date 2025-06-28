set dotenv-load

# List commands, default
default:
  just --list

# Initialize by installing deps and copying the env file
init:
    uv sync
    @if [ -f .env ]; then echo ".env file already exists!"; exit 1; fi
    cp .env.example .env
    nano .env

# Step 1: Collect data from all sources
collect:
    uv run collect_data.py

# Step 1: Collect data from one source
collect-one source:
    uv run collect_data.py --source {{source}}

# Step 2: Evaluate collected data with LLM
evaluate:
    uv run evaluate_data.py

# Step 2: Force re-evaluation of all items
evaluate-force:
    uv run evaluate_data.py --force

# Step 2: Evaluate indefinitely
evaluate-forever:
    uv run evaluate_data.py --rounds inf

# Complete workflow: collect then evaluate
workflow: collect evaluate

# Migrate existing digest_results.json to new two-step format
migrate:
    uv run migrate_data.py

# Serve the web view
web:
    @if [ ! -f digest_results.json ]; then echo "Results missing! Run the loaders first."; exit 1; fi
    @echo "Starting web server on http://localhost:8000"
    python3 -m http.server -b localhost 8000
