# NL2SQL Data Agent

## Setup

```bash
# Clone the repository
git clone https://github.com/momalekpour/vortosql.git
cd vortosql

# Install dependencies (uv manages the virtualenv and Python version automatically)
# Install uv first if needed: https://docs.astral.sh/uv/getting-started/installation/
uv sync --all-extras

# (Optional) Install pre-commit hooks for auto linting (ruff) and formatting (black) for development
uv run pre-commit install
```

## Run

```bash
# Copy the example env file and set your OPENAI_API_KEY
cp .env.example .env

# Web UI (recommended) 
bash scripts/run_ui.sh

# CLI REPL
bash scripts/run_cli.sh
```

## Architecture

### Pipeline Overview

See [`docs/architecture.md`](docs/architecture.md) for full details. The application is built around a **composable operator pipeline** configured via `config.yaml` — each operator's model provider, technique, and behaviour is plug-and-play; the default setup is ready to run as-is. Each operator implements an `execute(context)` method that reads from and writes to a shared context dictionary. The pipeline runs the following operators in order:

1. **IntentGuardrail** - LLM-based scope classifier; rejects out-of-scope questions via early-stop
2. **SchemaLinker** - Resolves which tables/columns are relevant to the question
3. **ExampleSelector** - Retrieves similar few-shot examples (skipped in zero-shot mode)
4. **SQLGenerator** - LLM generates a SQL query from the question, schema, and examples
5. **SQLCorrector** - Validates and auto-corrects SQL errors via retry loop
6. **SQLExecutor** - Executes the final SQL; enforces department guardrails via AST-level injection
7. **AnswerGenerator** - LLM summarises the query results into a natural language answer

### Guardrails System

Department is locked at session start and enforced across five independent layers:

- **Layer 0 — Intent gate** (IntentGuardrail, soft): LLM checks if the question is in-domain; triggers early-stop if not.
- **Layer 1 — Schema restriction** (SchemaLinker, hard): `schema_guardrails` hides tables/columns from the LLM entirely.
- **Layer 2 — Prompt constraint** (SQLGenerator, soft): `row_guardrails` are rendered as mandatory filter instructions in the prompt.
- **Layer 3a — Direct AST injection** (SQLExecutor, hard): sqlglot injects a missing `WHERE` on guardrailed columns (e.g., `Employee.Department = 'Engineering'`).
- **Layer 3b — FK-aware AST injection** (SQLExecutor, hard): sqlglot injects a subquery filter for child tables queried without a JOIN (e.g., `Certification.EmployeeId IN (SELECT ...)`).

### Session Logs

Each pipeline run dumps its full config and context to `logs/<timestamp>.json` for traceability.
