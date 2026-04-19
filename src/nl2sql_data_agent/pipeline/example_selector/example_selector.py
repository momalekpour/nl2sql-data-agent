import enum
import random
from typing import Any

from nl2sql_data_agent.core.logger import Logger
from nl2sql_data_agent.core.model_manager import ModelProvider, OpenAIModel, OllamaModel
from nl2sql_data_agent.pipeline.example_selector.question_similarity import (
    QuestionSimilarity,
    load_bird_mini_dev_examples,
)
from nl2sql_data_agent.pipeline.operator import Operator

logger = Logger(__name__)


class ExampleSelectionTechnique(enum.Enum):
    RANDOM = "random"
    QUESTION_SIMILARITY = "question_similarity"


class ExampleSelector(Operator):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

    def execute(self, context: dict[str, Any]) -> None:
        try:
            technique = self.config["technique"]

            technique_map = {
                ExampleSelectionTechnique.RANDOM: self._select_random_examples,
                ExampleSelectionTechnique.QUESTION_SIMILARITY: self._select_example_by_question_similarity,
            }
            method = technique_map[technique]
            context["example_selector_examples"] = method(**self.config, **context)
        except Exception as e:
            logger.log("error", "ERROR_IN_EXAMPLE_SELECTOR_OPERATOR", {"error": str(e)})
            raise

    @staticmethod
    def _select_random_examples(
        number_of_examples: int,
        random_seed: int | None = None,
        **kwargs,
    ) -> list[tuple[str, str | None, str]]:
        examples_list = load_bird_mini_dev_examples()

        if random_seed is not None:
            random.seed(random_seed)

        random_samples = random.sample(examples_list, number_of_examples)
        return [
            (
                sample["question"],
                sample.get("evidence"),
                sample.get("SQL"),
            )
            for sample in random_samples
        ]

    @staticmethod
    def _select_example_by_question_similarity(
        number_of_examples: int,
        embedding_model_provider: ModelProvider,
        embedding_model_name: OllamaModel | OpenAIModel,
        user_question: str,
        **kwargs,
    ) -> list[tuple[str, str | None, str]]:
        qs = QuestionSimilarity(
            embedding_model_provider,
            embedding_model_name,
        )
        return qs.select_examples(number_of_examples, user_question)


if __name__ == "__main__":
    # ad-hoc testing
    print("=== RANDOM SELECTION ===")
    selector = ExampleSelector(
        config={
            "technique": ExampleSelectionTechnique.RANDOM,
            "number_of_examples": 3,
            "random_seed": 42,
        }
    )
    context: dict[str, Any] = {}
    selector.execute(context)
    for i, (question, evidence, sql) in enumerate(
        context["example_selector_examples"], 1
    ):
        print(f"\n[{i}] Question : {question}")
        print(f"    Evidence : {evidence}")
        print(f"    SQL      : {sql}")

    print("\n=== QUESTION SIMILARITY SELECTION ===")
    similarity_selector = ExampleSelector(
        config={
            "technique": ExampleSelectionTechnique.QUESTION_SIMILARITY,
            "number_of_examples": 3,
            "embedding_model_provider": ModelProvider.OPENAI,
            "embedding_model_name": OpenAIModel.TEXT_EMBEDDING_3_SMALL,
        }
    )
    similarity_context: dict[str, Any] = {
        "user_question": "What is the total revenue for each product category in 2023?"
    }
    similarity_selector.execute(similarity_context)

    for i, (question, evidence, sql) in enumerate(
        similarity_context["example_selector_examples"], 1
    ):
        print(f"\n[{i}] Question : {question}")
        print(f"    Evidence : {evidence}")
        print(f"    SQL      : {sql}")
