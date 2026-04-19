from typing import Any

import sqlglot
from sqlglot import exp

from nl2sql_data_agent.core.database.database_handler import DatabaseHandler
from nl2sql_data_agent.core.logger import Logger
from nl2sql_data_agent.pipeline.operator import Operator

logger = Logger(__name__)


class SQLExecutor(Operator):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

    def execute(self, context: dict[str, Any]) -> None:
        sql_query = context.get("sql_query", "")
        try:
            row_guardrails = context.get("row_guardrails")
            if row_guardrails:
                sql_query = self._inject_guardrails(
                    sql_query, row_guardrails, self.config["dbms"].value
                )

            db = DatabaseHandler(
                self.config["dbms"], {"db_path": self.config["db_file_path"]}
            )
            try:
                columns, rows = db.run_query(sql_query)
            finally:
                db.close_connection()

            context["sql_executor_sql_query"] = sql_query
            context["sql_executor_columns"] = list(columns)
            context["sql_executor_rows"] = [list(r) for r in rows]
            context["sql_executor_row_count"] = len(rows)
            context["sql_executor_error"] = None

            logger.log(
                "info",
                "SQL_EXECUTED_SUCCESSFULLY",
                {"row_count": len(rows), "sql_query": sql_query},
            )
        except Exception as e:
            logger.log("error", "ERROR_IN_SQL_EXECUTOR_OPERATOR", {"error": str(e)})
            context["sql_executor_sql_query"] = sql_query
            context["sql_executor_columns"] = []
            context["sql_executor_rows"] = []
            context["sql_executor_row_count"] = 0
            context["sql_executor_error"] = str(e)

    @staticmethod
    def _inject_guardrails(
        sql: str, row_guardrails: dict[str, dict[str, Any]], dialect: str
    ) -> str:
        """Inject missing WHERE conditions from row_guardrails into the SQL AST.

        For each (table, {col: val}) pair, finds the table's alias in the query
        and appends the condition if it isn't already present.
        """
        try:
            ast = sqlglot.parse_one(sql, dialect=dialect)
        except sqlglot.errors.ParseError:
            return sql  # can't parse → return as-is, let DB surface the error

        # Build table_name (lower) → alias_or_name map
        table_alias_map: dict[str, str] = {
            table.name.lower(): table.alias_or_name for table in ast.find_all(exp.Table)
        }

        new_conditions: list[exp.Expression] = []
        for table_name, filters in row_guardrails.items():
            alias = table_alias_map.get(table_name.lower())
            if alias is None:
                continue
            for col, val in filters.items():
                new_conditions.append(
                    exp.EQ(
                        this=exp.Column(
                            this=exp.Identifier(this=col, quoted=False),
                            table=exp.Identifier(this=alias, quoted=False),
                        ),
                        expression=exp.Literal.string(str(val)),
                    )
                )

        if not new_conditions:
            return sql

        combined: exp.Expression = new_conditions[0]
        for cond in new_conditions[1:]:
            combined = exp.And(this=combined, expression=cond)

        existing_where = ast.find(exp.Where)
        if existing_where:
            ast.set(
                "where",
                exp.Where(this=exp.And(this=existing_where.this, expression=combined)),
            )
        else:
            ast.set("where", exp.Where(this=combined))

        return ast.sql(dialect=dialect)
