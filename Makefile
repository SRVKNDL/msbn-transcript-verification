# MSBN Transcript Verification — project-level convenience targets.
#
# Prerequisites:
#   Python 3.11+, Node 20, AWS CDK CLI (npm install -g aws-cdk)
#
# Do NOT run `deploy` without team review. See CLAUDE.md budget constraints.

# Resolve the Python interpreter: prefer python3.11 if available, fall back to python3.
PYTHON := $(shell command -v python3.11 2>/dev/null || command -v python3)

# Absolute path to the infra venv — required so VIRTUAL_ENV matches sys.prefix exactly.
INFRA_VENV := $(abspath infra/.venv)

.PHONY: install synth test lint clean

# ── install ────────────────────────────────────────────────────────────────────
# Set up Python venv for CDK infra, install per-Lambda deps, and install
# Node deps for the frontend.  Does NOT run pip/npm on the CI runner or
# activate any virtual environment in the shell.
install:
	@echo "==> using Python: $(PYTHON)"
	@echo "==> infra: creating venv and installing CDK deps"
	$(PYTHON) -m venv infra/.venv
	infra/.venv/bin/pip install --quiet --upgrade pip
	infra/.venv/bin/pip install --quiet -r infra/requirements.txt
	@echo "==> services: installing per-Lambda deps"
	@for svc in services/*/; do \
	    echo "    $$svc"; \
	    $(PYTHON) -m venv $$svc.venv; \
	    $$svc.venv/bin/pip install --quiet -r $$svc/requirements.txt; \
	done
	@echo "==> tests: installing pytest"
	$(PYTHON) -m venv .venv-test
	.venv-test/bin/pip install --quiet pytest
	@echo "==> frontend: installing Node deps"
	cd frontend && npm install

# ── synth ──────────────────────────────────────────────────────────────────────
# Synthesize CloudFormation templates into cdk.out/ without deploying.
# Safe to run locally; generates no AWS charges.
# Requires: make install (creates infra/.venv) and cdk CLI (npm install -g aws-cdk).
synth:
	@echo "==> cdk synth (no deployment)"
	@test -d infra/.venv || (echo "ERROR: run 'make install' first" && exit 1)
	cd infra && VIRTUAL_ENV=$(INFRA_VENV) PATH=$(INFRA_VENV)/bin:$$PATH JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk synth

# ── test ───────────────────────────────────────────────────────────────────────
# Run the full pytest suite.  No AWS credentials required — all handlers
# are stubs at this stage.
test:
	@echo "==> pytest"
	.venv-test/bin/pytest

# ── lint ───────────────────────────────────────────────────────────────────────
# Lint Python with ruff (fast, zero-config) and TypeScript with tsc.
# Install ruff: sudo pacman -S ruff  (or: pip install ruff)
lint:
	@echo "==> ruff (Python)"
	ruff check services/ tests/ infra/
	@echo "==> tsc (TypeScript)"
	cd frontend && npx tsc --noEmit

# ── clean ──────────────────────────────────────────────────────────────────────
# Remove generated artifacts.  Does NOT delete .venv directories (those are
# created by `install` and can be reused).
clean:
	@echo "==> removing cdk.out, __pycache__, dist, .pytest_cache"
	rm -rf infra/cdk.out
	rm -rf frontend/dist
	find . -type d -name __pycache__ -not -path './.git/*' -exec rm -rf {} +
	find . -type d -name .pytest_cache -not -path './.git/*' -exec rm -rf {} +
	find . -type d -name '*.egg-info' -not -path './.git/*' -exec rm -rf {} +
