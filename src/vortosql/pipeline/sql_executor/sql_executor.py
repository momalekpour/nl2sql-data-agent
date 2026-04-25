from typing import Any

import sqlglot
from sqlglot import exp

from vortosql.core.database.database_handler import DatabaseHandler
from vortosql.core.logger import Logger
from vortosql.pipeline.operator import Operator

logger = Logger(__name__)


class SQLExecutor(Operator):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

    def execute(self, context: dict[str, Any]) -> None:
        sql_query = context.get("sql_query", "")
        try:
            row_guardrails = context.get("row_guardrails")
            fk_guardrails = context.get("fk_guardrails")
            dialect = self.config["dbms"].value
            if row_guardrails:
                sql_query = self._inject_guardrails(sql_query, row_guardrails, dialect)
            if fk_guardrails and row_guardrails:
                sql_query = self._inject_fk_guardrails(
                    sql_query, fk_guardrails, row_guardrails, dialect
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
    def _is_inside_subquery(node: exp.Expression) -> bool:
        """Walk up the AST to check if a node is nested inside a subquery."""
        parent = node.parent
        while parent:
            if isinstance(parent, exp.Subquery):
                return True
            parent = parent.parent
        return False

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

        # Build table_name (lower) → alias_or_name map from top-level tables only.
        # ast.find_all(exp.Table) walks into subqueries too — if the LLM already
        # added a subquery like "WHERE EmployeeId IN (SELECT ... FROM Employee ...)",
        # we'd incorrectly inject Employee.Department on the outer WHERE where
        # Employee isn't a real FROM/JOIN table.
        table_alias_map: dict[str, str] = {}
        for table in ast.find_all(exp.Table):
            if SQLExecutor._is_inside_subquery(table):
                continue  # skip tables nested inside subqueries
            table_alias_map[table.name.lower()] = table.alias_or_name

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

    @staticmethod
    def _inject_fk_guardrails(
        sql: str,
        fk_guardrails: dict[str, dict[str, str]],
        row_guardrails: dict[str, dict[str, Any]],
        dialect: str,
    ) -> str:
        """Inject subquery filters for FK-related tables whose parent is absent.

        For example, if Certification appears without Employee, injects:
        WHERE <alias>.EmployeeId IN (
            SELECT EmployeeId FROM Employee WHERE Department = 'X'
        )
        """
        try:
            ast = sqlglot.parse_one(sql, dialect=dialect)
        except sqlglot.errors.ParseError:
            return sql

        table_alias_map: dict[str, str] = {}
        for table in ast.find_all(exp.Table):
            if SQLExecutor._is_inside_subquery(table):
                continue
            table_alias_map[table.name.lower()] = table.alias_or_name

        new_conditions: list[exp.Expression] = []
        for child_table, fk in fk_guardrails.items():
            child_alias = table_alias_map.get(child_table.lower())
            if child_alias is None:
                continue  # child table not in query, nothing to guard

            ref_table = fk["ref_table"]
            if ref_table.lower() in table_alias_map:
                continue  # parent in query — _inject_guardrails already handled it

            parent_filters = row_guardrails.get(ref_table, {})
            if not parent_filters:
                continue

            # Build: WHERE <child_alias>.<fk_column> IN (
            #   SELECT <ref_column> FROM <ref_table> WHERE <col> = '<val>' AND ...
            # )
            parent_conditions = [
                exp.EQ(
                    this=exp.Column(
                        this=exp.Identifier(this=col, quoted=False),
                        table=exp.Identifier(this=ref_table, quoted=False),
                    ),
                    expression=exp.Literal.string(str(val)),
                )
                for col, val in parent_filters.items()
            ]
            combined_parent = parent_conditions[0]
            for cond in parent_conditions[1:]:
                combined_parent = exp.And(this=combined_parent, expression=cond)

            subquery = (
                exp.Select(
                    expressions=[
                        exp.Column(this=exp.Identifier(this=fk["ref_column"]))
                    ],
                )
                .from_(
                    exp.Table(this=exp.Identifier(this=ref_table)),
                )
                .where(combined_parent)
            )

            in_condition = exp.In(
                this=exp.Column(
                    this=exp.Identifier(this=fk["fk_column"], quoted=False),
                    table=exp.Identifier(this=child_alias, quoted=False),
                ),
                expressions=[subquery],
            )
            new_conditions.append(in_condition)

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
