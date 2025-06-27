set dotenv-load

# List commands, default
default:
  just --list

# Run the full digest
run:
    uv run main.py

# Initialize by installing deps and copying the env file
init:
    uv sync
    @if [ -f .env ]; then echo ".env file already exists!"; exit 1; fi
    cp .env.example .env
    nano .env
