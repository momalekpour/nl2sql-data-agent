# NL2SQL Data Agent

## Setup Environment

**1. Clone the Repository**

Clone the project repository to your local machine using:

```bash
git clone https://github.com/momalekpour/nl2sql-data-agent.git
cd nl2sql-data-agent
```

 **2. Installation**

You will first need to install `uv` to manage dependencies. Follow the instructions at the official [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/). Once `uv` is installed, run the following command to install all dependencies, including optional ones for development:

```bash
uv sync --all-extras
```

This will automatically create and manage a virtual environment and fetch the appropriate Python version. No manual activation is needed — the run scripts use `uv run` to execute within the environment.

<details>
<summary>development setup</summary>

Install the `pre-commit` hooks for automatic linting (`ruff`) and formatting (`black`):

```bash
uv run pre-commit install
```

</details>

## How to Run

**1. Set Environment Variables**

Copy the example environment file and add your API key:

```bash
cp .env.example .env
```

Edit `.env` and set your `OPENAI_API_KEY`.

**2. Run the Web UI** _(recommended)_

```bash
bash scripts/run_ui.sh
```

This launches a Streamlit chat interface. Select your department from the sidebar and start asking questions.

**3. Run the CLI**

```bash
bash scripts/run_cli.sh
```

On startup, select a department (Engineering, Sales, Marketing, or Random). All subsequent queries are automatically restricted to that department. Type your natural language question and the agent will generate SQL, execute it, and display the results. Type `exit` or `quit` to stop.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for full details. The application is built around a **composable operator pipeline** configured via `config.yaml` — each operator's model provider, technique, and behaviour is plug-and-play; the default setup is ready to run as-is. Each operator implements an `execute(context)` method that reads from and writes to a shared context dictionary. The pipeline runs the following operators in order:

1. **IntentGuardrail** - LLM-based scope classifier; rejects out-of-scope questions via early-stop
2. **SchemaLinker** - Resolves which tables/columns are relevant to the question
3. **ExampleSelector** - Retrieves similar few-shot examples (skipped in zero-shot mode)
4. **SQLGenerator** - LLM generates a SQL query from the question, schema, and examples
5. **SQLCorrector** - Validates and auto-corrects SQL errors via retry loop
6. **SQLExecutor** - Executes the final SQL; enforces department guardrails via two AST-level injections: direct `WHERE` on Employee, and subquery `IN (...)` for Certification/Benefits when queried without a JOIN
7. **AnswerGenerator** - LLM summarises the query results into a natural language answer

Department enforcement uses a five-layer guardrail system: intent gating, schema restriction, prompt-level constraints, direct AST WHERE injection, and FK-aware subquery injection. See [`docs/architecture.md#guardrails`](docs/architecture.md#guardrails) for details.

## AI Tools Used

- **GitHub Copilot** - Used for inline code suggestions and autocompletion in PyCharm IDE
- **Claude Code** - Assisted with brainstorming, parts of the development including the web UI, codebase cleanup, and documentation
