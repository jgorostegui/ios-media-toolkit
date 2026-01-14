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

# === Testing ===

# Run all tests
test *ARGS:
    uv run pytest tests/ {{ARGS}}

# Run tests with coverage (mirrors CI)
test-cov:
    uv run pytest --cov=src/ios_media_toolkit --cov-report=term-missing --cov-report=xml -m "not integration"

# Run a single test file
test-file FILE:
    uv run pytest {{FILE}} -v

# === Linting & Formatting ===

# Check lint issues (no fix)
lint:
    uv run ruff check src tests

# Check format issues (no fix)
fmt-check:
    uv run ruff format --check src tests

# Auto-fix lint issues
lint-fix:
    uv run ruff check --fix src tests

# Auto-format code
fmt:
    uv run ruff format src tests

# Fix all lint and format issues
fix: fmt lint-fix

# === CI Commands ===

# Run all checks exactly as CI does (use before pushing)
ci: lint fmt-check test-cov

# Alias for ci
check: ci

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
