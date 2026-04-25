import math
import os
from typing import Any, List, Tuple, Union

import numpy as np
from datasets import load_dataset
from numpy import dtype, floating, ndarray

from vortosql.core.logger import Logger
from vortosql.core.model_manager import (
    ModelManager,
    ModelProvider,
    ModelType,
    OllamaModel,
    OpenAIModel,
)

logger = Logger(__name__)

_DATASET_CACHE_DIR = "data/cache/huggingface/datasets"
_examples_cache: list | None = None


def load_bird_mini_dev_examples() -> list:
    global _examples_cache
    if _examples_cache is None:
        ds = load_dataset("birdsql/bird_mini_dev", cache_dir=_DATASET_CACHE_DIR)
        _examples_cache = list(ds["mini_dev_sqlite"])
    return _examples_cache  # type: ignore[return-value]


class QuestionSimilarity:
    example_embeddings = None
    example_norms = None

    def __init__(
        self,
        model_provider: ModelProvider,
        model_name: Union[OllamaModel, OpenAIModel],
    ) -> None:
        self.model_provider = model_provider
        self.task_type = ModelType.EMBEDDING
        self.model_name = model_name
        self.examples_list = load_bird_mini_dev_examples()

        if (
            QuestionSimilarity.example_embeddings is None
            or QuestionSimilarity.example_norms is None
        ):
            QuestionSimilarity.example_embeddings, QuestionSimilarity.example_norms = (
                self._calculate_example_embeddings_and_norms()
            )

        self.example_embeddings = QuestionSimilarity.example_embeddings
        self.example_norms = QuestionSimilarity.example_norms

    def _calculate_query_embedding_and_norm(
        self,
        user_question: str,
    ) -> tuple[ndarray[Any, dtype[Any]], floating[Any]]:
        embedding_model = ModelManager.create_model(
            model_provider=self.model_provider,
            model_type=self.task_type,
            model_name=self.model_name,
            openai_api_key=os.getenv("OPENAI_API_KEY", None),
        )
        try:
            query_embedding = embedding_model.get_embedding(user_question)
            query_embedding_vector = np.array(query_embedding)
            query_norm = np.linalg.norm(query_embedding_vector)
            return query_embedding_vector, query_norm
        except Exception as e:
            logger.log("error", "QUERY_EMBEDDING_RETRIEVAL_FAILED", {"error": str(e)})
            raise

    @staticmethod
    def get_embeddings_in_batches(questions, embedding_model, batch_size: int = 2048):
        num_batches = math.ceil(len(questions) / batch_size)
        all_embeddings = []

        for i in range(num_batches):
            start_index = i * batch_size
            end_index = start_index + batch_size
            try:
                embeddings = embedding_model.get_embedding(
                    questions[start_index:end_index]
                )
                all_embeddings.extend(embeddings)
            except Exception as e:
                logger.log(
                    "error",
                    "BATCH_EMBEDDING_RETRIEVAL_FAILED",
                    {"batch": i, "error": str(e)},
                )
                raise

        return all_embeddings

    def select_examples(
        self, k: int, user_question: str
    ) -> List[Tuple[str, str | None, str]]:
        query_embedding, query_norm = self._calculate_query_embedding_and_norm(
            user_question
        )
        similarities = np.dot(self.example_embeddings, query_embedding) / (
            self.example_norms * query_norm
        )
        sorted_indices = np.argsort(similarities)[::-1]
        selected_examples = [
            (
                self.examples_list[int(idx)]["question"],
                self.examples_list[int(idx)].get("evidence"),
                self.examples_list[int(idx)].get("SQL"),
            )
            for idx in sorted_indices
        ][:k]
        return selected_examples

    def _calculate_example_embeddings_and_norms(self) -> Tuple[np.ndarray, np.ndarray]:
        questions = [example["question"] for example in self.examples_list]
        embedding_model = ModelManager.create_model(
            model_provider=self.model_provider,
            model_type=self.task_type,
            model_name=self.model_name,
            openai_api_key=os.getenv("OPENAI_API_KEY", None),
        )
        embeddings = QuestionSimilarity.get_embeddings_in_batches(
            questions, embedding_model
        )
        example_embeddings = np.array(embeddings)
        example_norms = np.linalg.norm(example_embeddings, axis=1)
        return example_embeddings, example_norms
