# ios-media-toolkit justfile
# Run `just` to see available recipes

# Default recipe - show help
default:
    @just --list

# Install dependencies
install:
    uv sync --all-extras --dev

# Run the CLI
run *ARGS:
    uv run imt {{ARGS}}

# Run all tests
test *ARGS:
    uv run pytest tests/ {{ARGS}}

# Run tests with coverage
test-cov:
    uv run pytest --cov=src/ios_media_toolkit --cov-report=term-missing -m "not integration"

# Run a single test file
test-file FILE:
    uv run pytest {{FILE}} -v

# Run linter
lint:
    uv run ruff check src tests

# Run formatter check
fmt-check:
    uv run ruff format --check src tests

# Format code
fmt:
    uv run ruff format src tests

# Run all checks (lint + format + test)
check: lint fmt-check test

# Build package
build:
    uv build

# Build Docker image
docker-build:
    docker build -t imt .

# Run Docker image (CPU mode)
docker-run *ARGS:
    docker run -v $(pwd):/media imt {{ARGS}}

# Run Docker image with GPU
docker-run-gpu *ARGS:
    docker run --gpus all -v $(pwd):/media imt {{ARGS}}

# Check system dependencies
check-deps:
    uv run imt check

# List encoding profiles
profiles:
    uv run imt list-profiles

# Clean build artifacts
clean:
    rm -rf dist/ build/ *.egg-info .pytest_cache .coverage coverage.xml htmlcov/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
