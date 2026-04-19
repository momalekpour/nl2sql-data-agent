import enum
import json
import os
from collections import defaultdict
from copy import copy
from dataclasses import dataclass
from typing import Any

from nl2sql_data_agent.core.database.database_handler import DatabaseHandler, DBMS
from nl2sql_data_agent.core.logger import logger
from nl2sql_data_agent.core.model_manager import OpenAIModel
from nl2sql_data_agent.core.model_manager.model_manager import (
    ModelManager,
    ModelProvider,
    ModelType,
)
from nl2sql_data_agent.core.model_manager.ollama_model import OllamaModel
from nl2sql_data_agent.core.model_manager.utils import compose_chat_messages
from nl2sql_data_agent.core.prompt_renderer import PromptRenderer
from nl2sql_data_agent.pipeline.operator import Operator

logger = logger.Logger(__name__)


class SchemaLinkingTechnique(enum.Enum):
    FULL = "full"
    TCSL = "tcsl"
    SCSL = "scsl"


@dataclass
class Column:
    table_name: str
    column_name: str
    column_type: str


@dataclass
class Table:
    table_name: str
    columns: list[Column]
    primary_keys: list[Column]


@dataclass
class ForeignKey:
    referencing_table: str
    referenced_table: str
    column: Column
    referenced_column: Column


class SchemaLinker(Operator):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        db_file_path = config["db_file_path"]
        if not os.path.isfile(db_file_path):
            raise FileNotFoundError(
                f"SQLite database file not found: '{db_file_path}'. "
                "sqlite3.connect() silently creates an empty DB for missing paths — pass a valid file."
            )
        self.db_file_path = db_file_path
        self.tables: list[Table] = []
        self.foreign_keys: list[ForeignKey] = []
        self._prompt_renderer = PromptRenderer(
            templates_dir_path="src/nl2sql_data_agent/pipeline/schema_linker/prompt_templates"
        )
        self._read_schema()

    def execute(self, context: dict[str, Any]) -> None:
        try:
            technique = self.config["technique"]
            technique_map = {
                SchemaLinkingTechnique.FULL: self._link_full,
                SchemaLinkingTechnique.TCSL: self._link_tcsl,
                SchemaLinkingTechnique.SCSL: self._link_scsl,
            }
            method = technique_map[technique]
            schema, columns = method(**self.config, **context)
            context["schema_linker_db_schema"] = schema
            context["schema_linker_db_columns"] = columns
        except Exception as e:
            logger.log("error", "ERROR_IN_SCHEMA_LINKER_OPERATOR", {"error": str(e)})
            raise

    def _link_full(
        self,
        accessible_schema: dict[str, list[str]] | None = None,
        **kwargs,
    ) -> tuple[str, dict[str, list[str]]]:
        return self.get_full_schema_representation(accessible_schema=accessible_schema)

    def _link_tcsl(
        self,
        model_provider: ModelProvider,
        model_name: OpenAIModel | OllamaModel,
        user_question: str,
        accessible_schema: dict[str, list[str]] | None = None,
        **kwargs,
    ) -> tuple[str, dict[str, list[str]]]:
        return self.get_TCSL_filtered_schema_representation(
            user_question=user_question,
            model_provider=model_provider,
            model_name=model_name,
            accessible_schema=accessible_schema,
        )

    def _link_scsl(
        self,
        model_provider: ModelProvider,
        model_name: OpenAIModel | OllamaModel,
        user_question: str,
        accessible_schema: dict[str, list[str]] | None = None,
        **kwargs,
    ) -> tuple[str, dict[str, list[str]]]:
        return self.get_SCSL_filtered_schema_representation(
            user_question=user_question,
            model_provider=model_provider,
            model_name=model_name,
            accessible_schema=accessible_schema,
        )

    def _read_schema(self):
        db = DatabaseHandler(DBMS.SQLITE, {"db_path": self.db_file_path})
        try:
            _, table_rows = db.run_query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            table_names = [row[0] for row in table_rows]
            column_map: dict[tuple[str, str], Column] = {}
            for table_name in table_names:
                _, rows = db.run_query(f"PRAGMA table_info('{table_name}')")
                # rows: (cid, name, type, notnull, dflt_value, pk)
                columns = [
                    Column(
                        table_name=table_name,
                        column_name=row[1],
                        column_type=row[2] or "TEXT",
                    )
                    for row in rows
                ]
                primary_keys = [col for col, row in zip(columns, rows) if row[5] > 0]
                self.tables.append(Table(table_name, columns, primary_keys))
                for col in columns:
                    column_map[(table_name, col.column_name)] = col

            for table_name in table_names:
                _, rows = db.run_query(f"PRAGMA foreign_key_list('{table_name}')")
                for row in rows:
                    # row: (id, seq, table, from, to, on_update, on_delete, match)
                    from_col = column_map.get((table_name, row[3]))
                    to_col = column_map.get((row[2], row[4]))
                    if from_col and to_col:
                        self.foreign_keys.append(
                            ForeignKey(
                                referencing_table=table_name,
                                referenced_table=row[2],
                                column=from_col,
                                referenced_column=to_col,
                            )
                        )
        finally:
            db.close_connection()

    def _format_schema_description(
        self,
        tables: list[Table],
        columns_filter: dict[str, list[str]] | None = None,
        include_schema_overview: bool = True,
    ) -> str:
        schema_description = ""

        for table in tables:
            schema_description += f"\nTable '{table.table_name}':\n"

            table_columns = table.columns
            if columns_filter and table.table_name in columns_filter:
                table_columns = [
                    col
                    for col in table.columns
                    if col.column_name in columns_filter[table.table_name]
                ]

            for column in table_columns:
                schema_description += (
                    f"  - '{column.column_name}' ({column.column_type})\n"
                )

            table_primary_keys = defaultdict(list)
            for pk in table.primary_keys:
                if pk.table_name == table.table_name:
                    if not columns_filter or (
                        table.table_name in columns_filter
                        and pk.column_name in columns_filter[table.table_name]
                    ):
                        table_primary_keys[pk.table_name].append(pk.column_name)

            if table_primary_keys:
                for table_name, primary_keys in table_primary_keys.items():
                    pks = "', '".join([f"'{pk}'" for pk in primary_keys])
                    schema_description += f"  Primary keys: {pks}\n"

            table_foreign_keys = [
                (
                    fk.column.column_name,
                    fk.referenced_table,
                    fk.referenced_column.column_name,
                )
                for fk in self.foreign_keys
                if fk.referencing_table == table.table_name
                and (
                    not columns_filter
                    or (
                        table.table_name in columns_filter
                        and fk.column.column_name in columns_filter[table.table_name]
                        and fk.referenced_table in [t.table_name for t in tables]
                    )
                )
            ]

            if table_foreign_keys:
                schema_description += "  Foreign keys:\n"
                for fk_column, fk_table, fk_referenced_column in table_foreign_keys:
                    schema_description += f"    - '{fk_column}' referencing column '{fk_referenced_column}' in table '{fk_table}'\n"

        if include_schema_overview:
            schema_description += "\nSchema Overview:\n"
            for table in tables:
                table_columns = table.columns
                if columns_filter and table.table_name in columns_filter:
                    table_columns = [
                        col
                        for col in table.columns
                        if col.column_name in columns_filter[table.table_name]
                    ]

                columns_str = ", ".join(col.column_name for col in table_columns)
                if columns_str:
                    schema_description += f"{table.table_name} ({columns_str})\n"

            schema_description += "\n"

            table_names = {t.table_name for t in tables}
            for fk in self.foreign_keys:
                if (
                    fk.referencing_table in table_names
                    and fk.referenced_table in table_names
                ):
                    if not columns_filter or (
                        fk.column.column_name
                        in columns_filter.get(fk.referencing_table, [])
                        and fk.referenced_column.column_name
                        in columns_filter.get(fk.referenced_table, [])
                    ):
                        schema_description += (
                            f"{fk.referencing_table}.{fk.column.column_name} = "
                            f"{fk.referenced_table}.{fk.referenced_column.column_name}\n"
                        )

        return schema_description

    @staticmethod
    def _clean_json_response(response: str) -> str:
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        return response.strip()

    def _restrict_to_accessible(
        self, accessible_schema: dict[str, list[str]]
    ) -> list[Table]:
        """Return a filtered copy of self.tables restricted to accessible_schema.
        Never mutates self.tables or any Table/Column objects."""
        result = []
        for table in self.tables:
            if table.table_name not in accessible_schema:
                continue
            allowed = accessible_schema[table.table_name]
            restricted = copy(table)
            if "*" not in allowed:
                allowed_set = set(allowed)
                restricted.columns = [
                    c for c in table.columns if c.column_name in allowed_set
                ]
                restricted.primary_keys = [
                    pk for pk in table.primary_keys if pk.column_name in allowed_set
                ]
            if restricted.columns:
                result.append(restricted)
        return result

    def get_full_schema_representation(
        self,
        accessible_schema: dict[str, list[str]] | None = None,
    ) -> tuple[str, dict[str, list[str]]]:
        tables = (
            self._restrict_to_accessible(accessible_schema)
            if accessible_schema
            else self.tables
        )
        all_columns = {
            table.table_name: [col.column_name for col in table.columns]
            for table in tables
        }
        schema_description = self._format_schema_description(
            tables=tables, include_schema_overview=True
        )
        return schema_description, all_columns

    def get_gold_filtered_schema_representation(
        self, gold_tables: set, gold_columns: set
    ) -> tuple[str, dict[str, list[str]]]:
        filtered_columns = {}
        filtered_tables = []

        for table in self.tables:
            if table.table_name in gold_tables:
                filtered_tables.append(table)
                filtered_columns[table.table_name] = [
                    col.column_name
                    for col in table.columns
                    if col.column_name in gold_columns
                ]

        schema_description = self._format_schema_description(
            tables=filtered_tables,
            columns_filter=filtered_columns,
            include_schema_overview=True,
        )
        return schema_description, filtered_columns

    def get_number_of_tables(self) -> int:
        return len(self.tables)

    def get_number_of_columns(self) -> int:
        return sum(len(table.columns) for table in self.tables)

    def extract_relevant_tables(
        self,
        user_question: str,
        llm_provider: ModelProvider,
        model_name: OpenAIModel | OllamaModel,
        candidate_tables: list[Table] | None = None,
    ) -> tuple[list[Table], str]:
        tables = candidate_tables if candidate_tables is not None else self.tables
        full_schema = self._format_schema_description(
            tables=tables, include_schema_overview=True
        )
        context = {
            "user_question": user_question,
            "full_schema": full_schema,
        }
        prompt = self._prompt_renderer.render("TCSL_table_linking", context)
        messages = compose_chat_messages(user_messages=[prompt])
        llm = ModelManager.create_model(
            model_provider=llm_provider,
            model_type=ModelType.COMPLETION,
            model_name=model_name,
        )
        llm_response = llm.get_chat_completion(messages=messages, temperature=0)[
            "completion_content"
        ][0]
        llm_response = self._clean_json_response(llm_response)
        llm_tables = json.loads(llm_response)["tables"]
        llm_tables_lower = {t.lower() for t in llm_tables}
        filtered_tables = [
            t for t in tables if t.table_name.lower() in llm_tables_lower
        ]
        schema_description = self._format_schema_description(
            tables=filtered_tables, include_schema_overview=True
        )
        return filtered_tables, schema_description

    def extract_relevant_columns(
        self,
        filtered_tables_schema: str,
        filtered_tables: list[Table],
        user_question: str,
        llm_provider: ModelProvider,
        model_name: OpenAIModel | OllamaModel,
    ) -> tuple[list[Table], str, dict[str, list[str]]]:
        context = {
            "user_question": user_question,
            "filtered_tables_schema": filtered_tables_schema,
        }
        prompt = self._prompt_renderer.render("TCSL_column_linking", context)
        messages = compose_chat_messages(user_messages=[prompt])
        llm = ModelManager.create_model(
            model_provider=llm_provider,
            model_type=ModelType.COMPLETION,
            model_name=model_name,
        )
        llm_response = llm.get_chat_completion(messages=messages, temperature=0)[
            "completion_content"
        ][0]
        llm_response = self._clean_json_response(llm_response)
        data = json.loads(llm_response)

        all_filtered_columns = {}
        result_tables = []
        for table in filtered_tables:
            if table.table_name in data:
                allowed = set(data[table.table_name])
                all_filtered_columns[table.table_name] = [
                    col
                    for col in data[table.table_name]
                    if col in {c.column_name for c in table.columns}
                ]
                filtered = copy(table)
                filtered.columns = [
                    c for c in table.columns if c.column_name in allowed
                ]
                filtered.primary_keys = [
                    pk for pk in table.primary_keys if pk.column_name in allowed
                ]
                if filtered.columns:
                    result_tables.append(filtered)

        filtered_tables_columns = result_tables
        schema_description = self._format_schema_description(
            tables=filtered_tables_columns,
            columns_filter=all_filtered_columns,
            include_schema_overview=True,
        )
        return filtered_tables_columns, schema_description, all_filtered_columns

    def get_TCSL_filtered_schema_representation(
        self,
        user_question: str,
        model_provider: ModelProvider,
        model_name: OpenAIModel | OllamaModel,
        accessible_schema: dict[str, list[str]] | None = None,
    ) -> tuple[str, dict[str, list[str]]]:
        candidate_tables = (
            self._restrict_to_accessible(accessible_schema)
            if accessible_schema
            else None
        )
        filtered_tables, filtered_tables_schema = self.extract_relevant_tables(
            user_question, model_provider, model_name, candidate_tables
        )
        _, schema, all_columns = self.extract_relevant_columns(
            filtered_tables_schema,
            filtered_tables,
            user_question,
            model_provider,
            model_name,
        )
        return schema, all_columns

    def get_SCSL_filtered_schema_representation(
        self,
        user_question: str,
        model_provider: ModelProvider,
        model_name: OpenAIModel | OllamaModel,
        accessible_schema: dict[str, list[str]] | None = None,
    ) -> tuple[str, dict[str, list[str]]]:
        llm = ModelManager.create_model(
            model_provider=model_provider,
            model_type=ModelType.COMPLETION,
            model_name=model_name,
        )

        relevant_columns: dict[str, list[str]] = defaultdict(list)
        relevant_tables: set[str] = set()
        candidate_tables = (
            self._restrict_to_accessible(accessible_schema)
            if accessible_schema
            else self.tables
        )

        for table in candidate_tables:
            for column in table.columns:
                context = {
                    "user_question": user_question,
                    "candidate_column": f"{table.table_name}.{column.column_name}",
                }
                prompt = self._prompt_renderer.render("SCSL", context)
                messages = compose_chat_messages(user_messages=[prompt])
                llm_response = llm.get_chat_completion(
                    messages=messages, temperature=0
                )["completion_content"][0]
                llm_response = self._clean_json_response(llm_response)
                try:
                    response_data = json.loads(llm_response)
                    if response_data.get("relevant", False):
                        relevant_columns[table.table_name].append(column.column_name)
                        relevant_tables.add(table.table_name)
                except json.JSONDecodeError:
                    logger.log(
                        "error",
                        "FAILED_TO_PARSE_SCSL_RESPONSE",
                        {
                            "column": f"{table.table_name}.{column.column_name}",
                            "response": llm_response,
                        },
                    )

        filtered_tables = [
            t for t in candidate_tables if t.table_name in relevant_tables
        ]
        schema_description = self._format_schema_description(
            tables=filtered_tables,
            columns_filter=dict(relevant_columns),
            include_schema_overview=True,
        )
        return schema_description, dict(relevant_columns)


if __name__ == "__main__":
    # ad-hoc testing
    db_file_path = "data/employees.db"
    question = "What is the name of the employee with the highest salary?"

    accessible_schema = {
        "Employee": ["EmployeeId", "Name", "SalaryAmount", "Role"],
        "Certification": ["CertificationId"],
    }

    # Full schema — no LLM
    print("--------\nFull Schema (unrestricted)")
    linker = SchemaLinker(
        config={"db_file_path": db_file_path, "technique": SchemaLinkingTechnique.FULL}
    )
    ctx: dict[str, Any] = {}
    linker.execute(ctx)
    print(ctx["schema_linker_db_schema"])

    print("--------\nFull Schema (restricted)")
    linker = SchemaLinker(
        config={
            "db_file_path": db_file_path,
            "technique": SchemaLinkingTechnique.FULL,
            "accessible_schema": accessible_schema,
        }
    )
    ctx = {}
    linker.execute(ctx)
    print(ctx["schema_linker_db_schema"])
    print("Columns by table:", ctx["schema_linker_db_columns"])

    # TCSL — LLM only sees accessible tables/columns
    print("--------\nTCSL (restricted)")
    linker = SchemaLinker(
        config={
            "db_file_path": db_file_path,
            "technique": SchemaLinkingTechnique.TCSL,
            "model_provider": ModelProvider.OPENAI,
            "model_name": OpenAIModel.GPT_54_MINI,
            "accessible_schema": accessible_schema,
        }
    )
    ctx = {"user_question": question}
    linker.execute(ctx)
    print(ctx["schema_linker_db_schema"])
    print("Columns by table:", ctx["schema_linker_db_columns"])

    # SCSL — LLM evaluates columns only within accessible set
    print("--------\nSCSL (restricted)")
    linker = SchemaLinker(
        config={
            "db_file_path": db_file_path,
            "technique": SchemaLinkingTechnique.SCSL,
            "model_provider": ModelProvider.OPENAI,
            "model_name": OpenAIModel.GPT_54_MINI,
            "accessible_schema": accessible_schema,
        }
    )
    ctx = {"user_question": question}
    linker.execute(ctx)
    print(ctx["schema_linker_db_schema"])
    print("Columns by table:", ctx["schema_linker_db_columns"])
