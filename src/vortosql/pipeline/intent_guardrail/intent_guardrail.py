import json
from typing import Any

from vortosql.core.logger import Logger
from vortosql.core.model_manager import ModelManager, ModelType
from vortosql.core.model_manager.utils import compose_chat_messages
from vortosql.core.prompt_renderer import PromptRenderer
from vortosql.pipeline.operator import Operator

logger = Logger(__name__)


class IntentGuardrail(Operator):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._prompt_renderer = PromptRenderer(
            templates_dir_path="src/vortosql/pipeline/intent_guardrail/prompt_templates"
        )
        self._llm = ModelManager.create_model(
            model_provider=self.config["chat_completion_model_provider"],
            model_type=ModelType.COMPLETION,
            model_name=self.config["chat_completion_model_name"],
        )

    def execute(self, context: dict[str, Any]) -> None:
        user_question = context.get("user_question", "")
        try:
            prompt = self._prompt_renderer.render(
                "intent_check", {"user_question": user_question}
            )
            messages = compose_chat_messages(user_messages=[prompt])
            response = self._llm.get_chat_completion(
                messages=messages,
                temperature=self.config["temperature"],
            )
            raw = response["completion_content"][0].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            is_in_scope: bool = bool(data.get("is_in_scope", True))
            reason: str = data.get("reason", "")
        except Exception as e:
            # Fail open: if classification fails, let the pipeline continue
            logger.log(
                "warning",
                "INTENT_GUARDRAIL_FAILED",
                {"error": str(e), "question": user_question},
            )
            is_in_scope = True
            reason = ""

        context["intent_guardrail_is_in_scope"] = is_in_scope
        context["intent_guardrail_reason"] = reason

        if not is_in_scope:
            message = (
                "I can only answer questions about employee"
                " details, certifications, and benefits. "
                "Your question appears to be out of scope:"
                f" {reason}"
            )
            context["pipeline_early_stop"] = message
            logger.log(
                "info",
                "INTENT_OUT_OF_SCOPE",
                {"question": user_question, "reason": reason},
            )
        else:
            logger.log("info", "INTENT_IN_SCOPE", {"question": user_question})
