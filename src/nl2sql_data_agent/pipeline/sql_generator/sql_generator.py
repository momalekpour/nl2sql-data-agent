import enum
from typing import Any

from nl2sql_data_agent.core.logger import Logger
from nl2sql_data_agent.core.model_manager import ModelManager, ModelType
from nl2sql_data_agent.core.model_manager.utils import compose_chat_messages
from nl2sql_data_agent.core.prompt_renderer import PromptRenderer
from nl2sql_data_agent.pipeline.operator import Operator

logger = Logger(__name__)


class SQLGenerationPromptTemplate(enum.Enum):
    ZERO_SHOT = "zero_shot"
    FEW_SHOT = "few_shot"


class SQLGenerator(Operator):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.prompt_renderer = PromptRenderer(
            templates_dir_path="src/nl2sql_data_agent/pipeline/sql_generator/prompt_templates"
        )
        self.llm = ModelManager.create_model(
            model_provider=self.config["chat_completion_model_provider"],
            model_type=ModelType.COMPLETION,
            model_name=self.config["chat_completion_model_name"],
        )

    def execute(self, context: dict[str, Any]) -> None:
        try:
            prompt = self.prompt_renderer.render(
                self.config["prompt_template"].value, context
            )
            messages = compose_chat_messages(user_messages=[prompt])
            llm_response = self.llm.get_chat_completion(
                messages=messages,
                seed=self.config["random_seed"],
                temperature=self.config["temperature"],
            )

            sql_generator_llm_response = {
                f"sql_generator_{key}": value
                for key, value in llm_response.items()
                if key != "completion_content"
            }

            sql_query = self._clean_sql_query(llm_response["completion_content"][0])

            context.update(
                sql_generator_llm_response
                | {
                    "sql_generator_prompt": prompt,
                    "sql_generator_sql_query": sql_query,
                    "sql_query": sql_query,
                }
            )

            logger.log(
                "info",
                "SQL_QUERY_GENERATED_SUCCESSFULLY",
                {
                    "user_question": context["user_question"],
                    "sql_query": context["sql_generator_sql_query"],
                },
            )
        except Exception as e:
            logger.log(
                "error",
                "ERROR_IN_SQL_GENERATOR_OPERATOR",
                {
                    "user_question": context["user_question"],
                    "error": str(e),
                },
            )
            raise

    @staticmethod
    def _clean_sql_query(sql_query: str) -> str:
        """Flatten the SQL query by removing newlines and extra spaces and remove potential ```sql ``` tags."""
        lines = [line.strip() for line in sql_query.splitlines()]
        single_line_query = " ".join(lines)
        single_line_query = " ".join(single_line_query.split())
        clean_single_line_query = single_line_query.replace("```sql", "").replace(
            "```", ""
        )
        return clean_single_line_query
