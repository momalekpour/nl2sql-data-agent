from typing import Any

from vortosql.core.logger import Logger
from vortosql.core.model_manager import ModelManager, ModelType
from vortosql.core.model_manager.utils import compose_chat_messages
from vortosql.core.prompt_renderer import PromptRenderer
from vortosql.pipeline.operator import Operator

logger = Logger(__name__)


class AnswerGenerator(Operator):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._prompt_renderer = PromptRenderer(
            templates_dir_path="src/vortosql/pipeline/answer_generator/prompt_templates"
        )
        self._llm = ModelManager.create_model(
            model_provider=self.config["chat_completion_model_provider"],
            model_type=ModelType.COMPLETION,
            model_name=self.config["chat_completion_model_name"],
        )

    def execute(self, context: dict[str, Any]) -> None:
        if context.get("pipeline_early_stop"):
            return
        if context.get("sql_executor_error"):
            return
        if context.get("sql_executor_row_count", 0) == 0:
            return

        try:
            prompt = self._prompt_renderer.render("answer", context)
            messages = compose_chat_messages(user_messages=[prompt])
            llm_response = self._llm.get_chat_completion(
                messages=messages,
                temperature=self.config["temperature"],
            )

            answer = llm_response["completion_content"][0].strip()

            answer_generator_llm_response = {
                f"answer_generator_{key}": value
                for key, value in llm_response.items()
                if key != "completion_content"
            }

            context.update(
                answer_generator_llm_response
                | {
                    "answer_generator_answer": answer,
                    "answer_generator_prompt": prompt,
                }
            )

            logger.log(
                "info",
                "ANSWER_GENERATED_SUCCESSFULLY",
                {"user_question": context["user_question"]},
            )
        except Exception as e:
            logger.log(
                "error",
                "ERROR_IN_ANSWER_GENERATOR_OPERATOR",
                {"error": str(e)},
            )
            context["answer_generator_answer"] = None
