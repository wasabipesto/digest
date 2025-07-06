set dotenv-load

# List commands, default
default:
  just --list

# Initialize by installing deps and copying the env file
init:
    uv sync
    @if [ -f .env ]; then echo ".env file already exists!"; exit 1; fi
    cp .env.example .env
    $EDITOR .env; or nano .env

# Step 1: Collect data from all sources
collect:
    uv run collect_data.py

# Step 1: Collect data from one source
collect-one source:
    uv run collect_data.py --source {{source}}

# Step 2: Evaluate collected data with LLM
evaluate:
    uv run evaluate_data.py

# Step 2: Evaluate indefinitely
evaluate-forever:
    uv run evaluate_data.py --rounds inf

# Check the result file exists
_check_result_file_exists:
    @if [ ! -f digest_results.json ]; then echo "Results missing! Run the loaders first."; exit 1; fi

# Serve the web diagnostics view
web: _check_result_file_exists
    @echo "Starting Flask web server on http://127.0.0.1:5000"
    uv run app.py

# Generate email digest and save to file
email-save: _check_result_file_exists
    uv run send_email.py save

# Generate email digest and open in browser
email-preview: _check_result_file_exists
    uv run send_email.py preview

# Send email digest via Mailgun
email-send: _check_result_file_exists
    uv run send_email.py send

# Archive last week's results
archive-results:
    if [ -f digest_results.json ]; then \
        mkdir -p archive && \
        mv digest_results.json archive/digest_results_$(date +%Y%m%d).json; \
    fi


# Complete weekly workflow: archive, collect, evaluate, send
weekly: archive-results collect evaluate email-send
