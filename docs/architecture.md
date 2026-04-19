# Architecture

## Overview

A modular NL2SQL system that translates natural language questions into SQL queries, enforces row-level guardrails, executes the SQL against a SQLite database, and returns results. Built around a composable operator pipeline with an intent gate, three independent guardrail layers, and a generic early-stop mechanism.

---

## Project Structure

```
src/nl2sql_data_agent/
├── __main__.py                     # Module entry point — allows `python -m nl2sql_data_agent`
├── app.py                          # Session orchestration — picks department, builds pipeline, exposes ask()
├── cli.py                          # Interactive terminal REPL with formatted table output
├── ui.py                           # Streamlit web UI (landing page + sidebar + chat)
│
├── core/
│   ├── database/                   # DB connection and query execution
│   │   ├── database_handler.py     # Unified interface; factory over adapters
│   │   └── adapters/
│   │       ├── base_adapter.py     # ABC: connect(), run_query(), close_connection()
│   │       ├── sqlite_adapter.py
│   │       └── duckdb_adapter.py
│   ├── logger/                     # Structured JSON logger (loguru)
│   │   └── logger.py               # Logger(name).log(level, event, payload)
│   ├── model_manager/              # LLM provider abstraction
│   │   ├── model_manager.py        # Factory: ModelManager.create_model(provider, type, name)
│   │   ├── openai_model.py         # Chat completion + embeddings (OpenAI API)
│   │   ├── ollama_model.py         # Local models via Ollama
│   │   ├── anthropic_model.py      # Anthropic Claude (chat only)
│   │   ├── huggingface_model.py    # HuggingFace inference
│   │   └── utils.py                # compose_chat_messages helper
│   └── prompt_renderer/            # Jinja2 template renderer (StrictUndefined)
│       └── prompt_renderer.py      # PromptRenderer(templates_dir_path).render(name, context)
│
└── pipeline/
    ├── operator.py                 # Operator ABC: __init__(config), execute(context)
    ├── config.py                   # Pydantic config models for every operator + pipeline
    ├── nl2sql_pipeline.py          # Assembles and runs the operator chain; early-stop loop
    ├── intent_guardrail/          # Step 1: LLM scope gate — rejects out-of-domain questions
    ├── schema_linker/              # Step 2: schema extraction and optional LLM filtering
    ├── example_selector/           # Step 3 (optional): few-shot examples from BIRD dataset
    ├── sql_generator/              # Step 4: NL → SQL via LLM + Jinja2 prompt
    ├── sql_corrector/              # Step 5 (optional): syntax correction loop with sqlglot
    └── sql_executor/               # Step 6: AST guardrail injection + DB execution

config.yaml                         # Runtime configuration for all operators

scripts/
├── run_ui.sh                       # Sources .env, then launches Streamlit
├── run_cli.sh                      # Sources .env, then launches the CLI
└── load_dotenv.sh                  # Exports all vars from .env into the shell

data/
└── employees.db                    # SQLite database (Employee, Certification, Benefit tables)

docs/
└── architecture.md                 # This file
```

---

## Request Flow

```
User input (cli.py / ui.py)
    │
    ▼
NL2SQLApp.ask(user_question)          ← app.py
    │  injects row_guardrails = {"Employee": {"Department": "<dept>"}}
    ▼
NL2SQLPipeline.execute(user_question, accessible_schema, row_guardrails)
    │
    │  context = {user_question, accessible_schema, row_guardrails}  ← initial context
    │
    ├─► IntentGuardrail.execute(context)
    │       LLM scope check: is the question about employees, certifications, or benefits?
    │       writes: intent_guardrail_is_in_scope, intent_guardrail_reason
    │       if out of scope → sets pipeline_early_stop → pipeline breaks here
    │
    ├─► SchemaLinker.execute(context)
    │       writes: schema_linker_db_schema, schema_linker_db_columns
    │
    ├─► ExampleSelector.execute(context)   [only when prompt_template = few_shot]
    │       writes: example_selector_examples
    │
    ├─► SQLGenerator.execute(context)
    │       writes: sql_query, sql_generator_sql_query, sql_generator_prompt, LLM metadata
    │
    ├─► SQLCorrector.execute(context)      [only when max_correction_attempts > 0]
    │       writes: sql_query (corrected), sql_corrector_sql_query, sql_corrector_is_successful
    │
    └─► SQLExecutor.execute(context)
            reads: sql_query, row_guardrails
            injects missing WHERE conditions via sqlglot AST
            executes SQL against DB
            writes: sql_executor_sql_query, sql_executor_columns, sql_executor_rows,
                    sql_executor_row_count, sql_executor_error
    │
    ▼
context dict returned (+ pipeline_latency, timestamp)
```

All operators share a single mutable `context` dict. Each operator reads its inputs from context and writes its outputs back to it. Operator config is static (set at construction); per-request data flows through context only.

**Early-stop mechanism:** After each operator, the pipeline checks `context.get("pipeline_early_stop")`. If truthy, the loop breaks and the remaining operators are skipped. The string value is the human-readable reason. Any operator can trigger this — it is not specific to `IntentGuardrail`.

---

## Operator Reference

### 1. IntentGuardrail

The first operator in the pipeline. Uses an LLM to determine whether the user's question is within the supported domain before any expensive downstream work (schema reading, SQL generation) is done.

**Config (`IntentGuardrailConfig`):**

| Key | Type | Required |
|---|---|---|
| `chat_completion_model_provider` | `ModelProvider` | yes |
| `chat_completion_model_name` | model enum | yes |
| `temperature` | `float [0, 2]` | yes |

**Prompt template (`intent_check.jinja`):**

Describes the three queryable domains (Employee details, Certifications, Benefits), includes seven few-shot examples (five in-scope, two out-of-scope), and asks the LLM to return `{"is_in_scope": bool, "reason": str}`.

**Behaviour:**
- Parses the JSON response; strips markdown fences if present
- On JSON parse failure: **fails open** (`is_in_scope = True`) — false negatives are preferable to blocking valid questions
- When out of scope: sets `context["pipeline_early_stop"]` with a user-facing message, halting the pipeline immediately

**Context writes:** `intent_guardrail_is_in_scope` (bool), `intent_guardrail_reason` (str), `pipeline_early_stop` (str, only when out of scope)

---

### 2. SchemaLinker  *(schema restriction)*

Connects to the SQLite database at startup, reads the full schema (tables, columns, PKs, FKs) once via PRAGMA queries, and produces a textual schema description for downstream operators.

**Config (`SchemaLinkerConfig`):**

| Key | Type | Required |
|---|---|---|
| `db_file_path` | `str` | yes |
| `technique` | `SchemaLinkingTechnique` | yes |
| `model_provider` | `ModelProvider` | for TCSL/SCSL only |
| `model_name` | `OpenAIModel \| OllamaModel` | for TCSL/SCSL only |

Pydantic `model_validator` enforces that `model_provider` and `model_name` are present when technique is TCSL or SCSL.

**Techniques:**

| Technique | Description | LLM calls |
|---|---|---|
| `full` | Returns all tables and columns verbatim | 0 |
| `tcsl` | Two-step: LLM picks relevant tables, then relevant columns | 2 |
| `scsl` | Scores each column individually | N (one per column) |

**Guardrail — Layer 1 (schema restriction):**

Accepts `accessible_schema: dict[str, list[str]]` from context. Before any technique runs, `_restrict_to_accessible()` filters `self.tables` to only the allowed tables/columns using shallow copies — `self.tables` is never mutated. Pass `"*"` to allow all columns in a table. Tables absent from `accessible_schema` are invisible to the LLM entirely.

**Context writes:** `schema_linker_db_schema` (str), `schema_linker_db_columns` (dict[str, list[str]])

---

### 3. ExampleSelector *(optional)*

Selects few-shot SQL examples from the BIRD mini-dev HuggingFace dataset to include in the SQL generation prompt. On first run, the dataset is automatically downloaded from HuggingFace — this is a high-quality collection of NL→SQL pairs used as ground-truth examples for few-shot prompting. Subsequent runs use the local cache at `data/cache/huggingface/datasets/`.

Skipped entirely when `sql_generator.prompt_template = zero_shot` (the operator is not added to the operator list).

**Config (`ExampleSelectorConfig`):**

| Key | Type | Required |
|---|---|---|
| `technique` | `ExampleSelectionTechnique` | yes |
| `number_of_examples` | `int` | yes |
| `embedding_model_provider` | `ModelProvider` | for `question_similarity` |
| `embedding_model_name` | model enum | for `question_similarity` |
| `random_seed` | `int \| None` | no |

Pydantic `model_validator` enforces embedding fields when technique is `question_similarity`.

**Techniques:**

| Technique | Description |
|---|---|
| `random` | Randomly samples N examples; respects `random_seed` for reproducibility |
| `question_similarity` | Embeds the user question, returns N nearest-neighbour examples by cosine similarity |

**Context writes:** `example_selector_examples`

---

### 4. SQLGenerator

Renders a Jinja2 prompt template with the schema, examples (if any), and user question, then calls an LLM for SQL generation.

**Config (`SQLGeneratorConfig`):**

| Key | Type | Required |
|---|---|---|
| `prompt_template` | `SQLGenerationPromptTemplate` | yes |
| `chat_completion_model_provider` | `ModelProvider` | yes |
| `chat_completion_model_name` | model enum | yes |
| `temperature` | `float [0, 2]` | yes |
| `random_seed` | `int \| None` | no |

**Templates:**

| Template | Context variables used |
|---|---|
| `zero_shot` | `schema_linker_db_schema`, `user_question`, `row_guardrails` |
| `few_shot` | above + `example_selector_examples` |

**Guardrail — Layer 2 (prompt constraint):**

Both templates include a `row_guardrails` block that renders mandatory filter instructions for the LLM:

```jinja
{% if row_guardrails %}
### Mandatory Constraints ###
Your SQL MUST enforce the following filters — do not omit them under any circumstances:
{% for table, filters in row_guardrails.items() %}{% for col, val in filters.items() %}- {{ table }}.{{ col }} = '{{ val }}'
{% endfor %}{% endfor %}
{% endif %}
```

This is a cooperative constraint — it relies on LLM compliance. Layer 3 (SQLExecutor) is the hard enforcement backstop.

Post-processing: LLM output is stripped of markdown fences (` ```sql ``` `) and collapsed to a single line.

**Context writes:** `sql_query`, `sql_generator_sql_query`, `sql_generator_prompt`, plus prefixed LLM metadata keys (`sql_generator_model`, `sql_generator_latency`, `sql_generator_prompt_tokens`, etc.)

---

### 5. SQLCorrector *(optional)*

Validates the generated SQL by parsing it with sqlglot. If parsing fails, sends the SQL + error back to an LLM for correction. Repeats up to `max_correction_attempts` times.

Skipped when `max_correction_attempts = 0` (operator not added to operator list).

**Config (`SQLCorrectorConfig`):**

| Key | Type | Required |
|---|---|---|
| `prompt_template` | `SQLCorrectionPromptTemplate` | yes |
| `max_correction_attempts` | `int` | yes |
| `dbms` | `DBMS` | yes |
| `chat_completion_model_provider` | `ModelProvider` | yes |
| `chat_completion_model_name` | model enum | yes |
| `temperature` | `float [0, 2]` | yes |
| `random_seed` | `int \| None` | no |

**Context writes:** `sql_query` (corrected in-place), `sql_corrector_sql_query`, `sql_corrector_is_successful`, per-attempt metadata

---

### 6. SQLExecutor

The final operator. Enforces row-level guardrails deterministically at the AST level, then executes the SQL and writes results.

**Config (`SQLExecutorConfig`):**

| Key | Type | Required |
|---|---|---|
| `db_file_path` | `str` | yes |
| `dbms` | `DBMS` | yes |

**Guardrail — Layer 3 (AST injection — hard enforcement):**

`_inject_guardrails()` uses sqlglot to:
1. Parse the SQL into an AST (`parse_one`)
2. Build a map of `table_name.lower() → alias_or_name` by walking `exp.Table` nodes
3. For each `(table, {col: val})` pair in `row_guardrails`, construct an `exp.EQ` condition referencing the alias
4. Inject conditions that are missing into the WHERE clause (appended with AND), or create a new WHERE clause if none exists
5. Serialize back to SQL in the target dialect

If sqlglot cannot parse the SQL, the original string is returned as-is (DB will surface the error). This layer runs regardless of LLM behaviour — it is not bypassable by prompt manipulation.

On execution error: writes the error string to `sql_executor_error` and zero-fills the result fields; does not raise — callers handle gracefully.

**Context writes:** `sql_executor_sql_query` (final SQL after guardrail injection), `sql_executor_columns`, `sql_executor_rows`, `sql_executor_row_count`, `sql_executor_error`

---

## Guardrails

Four independent, layered defences — one intent gate plus three data-scoping layers:

| Layer | Operator | Mechanism | Strength |
|---|---|---|---|
| 0 — Intent gate | IntentGuardrail | LLM classifies whether the question is in-domain (employees / certifications / benefits). Out-of-scope questions halt the pipeline before any SQL is generated. | Soft — LLM-dependent; fails open on parse error to avoid blocking valid questions |
| 1 — Schema restriction | SchemaLinker | `accessible_schema` hides entire tables/columns from the LLM. It never sees what isn't in the allowlist. | Hard — the LLM cannot reference what it cannot see |
| 2 — Prompt constraint | SQLGenerator | `row_guardrails` rendered into the prompt as mandatory filter instructions | Soft — relies on LLM compliance |
| 3 — AST injection | SQLExecutor | sqlglot parses the SQL and injects missing WHERE conditions before execution | Hard — deterministic, LLM-independent, runs on every query |

In the default app configuration:
- Layer 0 is always active (IntentGuardrail is always first in the operator list)
- Layer 1 is optional (pass `accessible_schema=None` to skip)
- Layers 2 and 3 are always active when `row_guardrails` is set
- SQLExecutor's Layer 3 is the last line of defence — not bypassable by prompt manipulation

**Examples:**

- **Layer 0 (intent gate):** User asks *"What's the weather?"* → LLM flags out of scope → pipeline stops immediately, no SQL generated.

- **Layer 1 (schema restriction):** `accessible_schema = {"Employee": ["*"]}` → Benefits and Certification tables are hidden. The LLM physically cannot reference them — they don't exist in the schema it sees.

- **Layer 2 (prompt constraint):** Session is locked to Marketing. The prompt includes *"Your SQL MUST enforce: Employee.Department = 'Marketing'"*. LLM cooperates and adds the filter itself.

- **Layer 3 (AST injection):** Same session. LLM generates `SELECT Name FROM Employee ORDER BY SalaryAmount DESC LIMIT 1` (forgot the filter). SQLExecutor rewrites it to `SELECT Name FROM Employee WHERE Employee.Department = 'Marketing' ORDER BY SalaryAmount DESC LIMIT 1` before touching the database. Cross-department leakage is impossible.

---

## Application Layer

### `app.py` — `NL2SQLApp`

Owns session state for one department-scoped session:

- `__init__(config_path, department)`: Loads `config.yaml`, validates the department against `DEPARTMENTS = ["Engineering", "Sales", "Marketing"]`, falls back to `random.choice` if invalid/missing, logs the selection, constructs `row_guardrails`, builds `NL2SQLPipeline`.
- `ask(user_question) -> dict`: Delegates to `pipeline.execute(user_question, row_guardrails=self._row_guardrails)` and returns the full context dict.
- `department` property: Exposes the selected department name.

### `cli.py` — Terminal REPL

- Presents a numbered menu: `[1] Engineering  [2] Sales  [3] Marketing  [4] Random`
- Instantiates `NL2SQLApp` with the selected department
- Input loop: prompts for question → calls `app.ask()` → checks `pipeline_early_stop` first (prints the message and continues) → otherwise renders ASCII table via `_format_table()`
- Handles `exit`/`quit`, empty input, EOF, and KeyboardInterrupt cleanly

### `ui.py` — Streamlit UI

Three-phase flow:

1. **Landing page** (`"started" not in session_state`): Hero section with title, subtitle, and "Get Started →" button. On click: sets `started=True`, default department, empty history, reruns.
2. **Sidebar**: `st.radio` for department selection. On change: clears history and reruns. Caption shows active department scope.
3. **Chat page**: Replays `session_state["history"]` top-to-bottom (oldest first) as user/assistant message pairs. New questions submitted via `st.chat_input`. Each history entry is rendered as:
   - `st.warning(...)` if `early_stop` is set (out-of-scope rejection)
   - `st.error(...)` if a SQL execution error occurred
   - `st.info("No results found.")` for empty result sets
   - `st.dataframe(...)` with SQL + row count + latency caption otherwise

`@st.cache_resource` keyed by department string ensures each department reuses its `NL2SQLApp` instance across reruns.

---

## Core Utilities

### DatabaseHandler

Adapter pattern over SQLite and DuckDB:

```python
db = DatabaseHandler(DBMS.SQLITE, {"db_path": "data/employees.db"})
columns, rows = db.run_query("SELECT ...")
db.close_connection()
```

`DatabaseHandler.__init__` calls `connect()` immediately. Always call `close_connection()` in a `finally` block.

### ModelManager

Factory for LLM clients:

```python
llm = ModelManager.create_model(
    model_provider=ModelProvider.OPENAI,
    model_type=ModelType.COMPLETION,
    model_name=OpenAIModel.GPT_54_MINI,
)
response = llm.get_chat_completion(messages=..., temperature=0)
```

`ModelType.EMBEDDING` is also supported for providers that offer it.

### PromptRenderer

Jinja2 renderer with `StrictUndefined` (missing variables raise at render time, not silently):

```python
renderer = PromptRenderer(templates_dir_path="path/to/templates")
prompt = renderer.render("zero_shot", context)  # renders zero_shot.jinja
```

### Logger

Structured JSON logging via loguru:

```python
logger = Logger(__name__)
logger.log("info", "EVENT_NAME", {"key": "value"})
```

---

## Supported LLM Providers

| Provider | Chat Completion | Embeddings |
|---|---|---|
| OpenAI | yes | yes |
| Ollama (local) | yes | yes |
| Anthropic | yes | no |
| HuggingFace | yes | yes |

Provider and model are independently configurable per operator — e.g. use Ollama for schema linking and OpenAI for SQL generation.

---

## Configuration Reference

`config.yaml` — all keys map 1:1 to Pydantic models in `pipeline/config.py`, validated at startup:

```yaml
nl2sql_pipeline:
  intent_guardrail:
    chat_completion_model_provider: openai
    chat_completion_model_name: gpt-5.4-mini
    temperature: 0

  schema_linker:
    db_file_path: data/employees.db      # path to SQLite file (must exist)
    technique: full                       # "full" | "tcsl" | "scsl"
    model_provider: openai               # required for tcsl/scsl
    model_name: gpt-5.4-mini             # required for tcsl/scsl

  example_selector:
    technique: question_similarity        # "random" | "question_similarity"
    number_of_examples: 3
    embedding_model_provider: openai     # required for question_similarity
    embedding_model_name: text-embedding-3-small
    random_seed: null                    # integer or null

  sql_generator:
    prompt_template: zero_shot           # "zero_shot" | "few_shot"
    chat_completion_model_provider: openai
    chat_completion_model_name: gpt-5.4-mini
    temperature: 0
    random_seed: null

  sql_corrector:
    max_correction_attempts: 2           # 0 disables the operator entirely
    prompt_template: syntax_correction   # "syntax_correction"
    dbms: sqlite                         # "sqlite" | "duckdb"
    chat_completion_model_provider: openai
    chat_completion_model_name: gpt-5.4-mini
    temperature: 0
    random_seed: null

  sql_executor:
    db_file_path: data/employees.db
    dbms: sqlite                         # "sqlite" | "duckdb"
```

`example_selector` must always be present in the YAML even when `sql_generator.prompt_template = zero_shot` — it is skipped at runtime but still parsed by Pydantic.
