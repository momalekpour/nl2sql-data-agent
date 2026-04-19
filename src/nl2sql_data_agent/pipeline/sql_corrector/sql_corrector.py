import enum
from typing import Any

import sqlglot
from sqlglot.errors import ParseError

from nl2sql_data_agent.core.database import DBMS
from nl2sql_data_agent.core.logger import Logger
from nl2sql_data_agent.core.model_manager import ModelManager, ModelType
from nl2sql_data_agent.core.model_manager.utils import compose_chat_messages
from nl2sql_data_agent.core.prompt_renderer import PromptRenderer
from nl2sql_data_agent.pipeline.operator import Operator

logger = Logger(__name__)


class SQLCorrectionPromptTemplate(enum.Enum):
    SYNTAX_CORRECTION = "syntax_correction"


class SQLCorrector(Operator):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.prompt_renderer = PromptRenderer(
            templates_dir_path="src/nl2sql_data_agent/pipeline/sql_corrector/prompt_templates"
        )
        self.llm = ModelManager.create_model(
            model_provider=self.config["chat_completion_model_provider"],
            model_type=ModelType.COMPLETION,
            model_name=self.config["chat_completion_model_name"],
        )

    def execute(self, context: dict[str, Any]) -> None:
        try:
            technique_map = {
                SQLCorrectionPromptTemplate.SYNTAX_CORRECTION: self._correct_sql_syntax,
            }
            method = technique_map[self.config["prompt_template"]]
            context.update(method(**self.config, **context))
        except Exception as e:
            logger.log("error", "ERROR_IN_SQL_CORRECTOR_OPERATOR", {"error": str(e)})
            raise

    def _correct_sql_syntax(
        self,
        max_correction_attempts: int,
        dbms: DBMS,
        schema_linker_db_schema: str,
        user_question: str,
        sql_query: str,
        **kwargs,
    ) -> dict[str, Any]:
        attempt = 0
        is_parsable = False
        total_latency = 0
        total_input_tokens = 0
        total_output_tokens = 0
        prompt = None

        while attempt < max_correction_attempts:
            try:
                sqlglot.parse_one(
                    sql_query, dialect=dbms.value, error_level=sqlglot.ErrorLevel.RAISE
                )
                is_parsable = True
                break
            except ParseError as parsing_error:
                prompt_context = {
                    "dbms": dbms.value,
                    "schema_linker_db_schema": schema_linker_db_schema,
                    "user_question": user_question,
                    "sql_query": sql_query,
                    "parsing_error": str(parsing_error),
                }
                prompt = self.prompt_renderer.render(
                    self.config["prompt_template"].value, prompt_context
                )
                messages = compose_chat_messages(user_messages=[prompt])
                llm_response = self.llm.get_chat_completion(
                    messages=messages,
                    seed=self.config["random_seed"],
                    temperature=self.config["temperature"],
                )
                sql_query = self._flatten_sql_query(
                    llm_response["completion_content"][0]
                )
                total_latency += llm_response["completion_latency"]
                total_input_tokens += llm_response["num_input_tokens"]
                total_output_tokens += llm_response["num_output_tokens"]
                attempt += 1

        if is_parsable and attempt > 0:
            logger.log(
                "info",
                "SQL_QUERY_IS_PARSABLE_AFTER_CORRECTION_ATTEMPTS",
                {
                    "corrected_sql_query": sql_query,
                    "attempt": attempt,
                },
            )
        elif not is_parsable and attempt > 0:
            logger.log(
                "warning",
                "SQL_QUERY_IS_NOT_PARSABLE_AFTER_CORRECTION_ATTEMPTS",
                {
                    "unparsable_sql_query": sql_query,
                    "max_correction_attempts": max_correction_attempts,
                },
            )

        return {
            "sql_query": sql_query,
            "sql_corrector_sql_query": sql_query,
            "sql_corrector_prompt": prompt,
            "sql_corrector_is_successful": is_parsable,
            "sql_corrector_num_attempts": attempt,
            "sql_corrector_latency": total_latency,
            "sql_corrector_num_input_tokens": total_input_tokens,
            "sql_corrector_num_output_tokens": total_output_tokens,
        }

    @staticmethod
    def _flatten_sql_query(sql_query: str) -> str:
        lines = [line.strip() for line in sql_query.splitlines()]
        single_line_query = " ".join(lines)
        single_line_query = " ".join(single_line_query.split())
        return single_line_query
