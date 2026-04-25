from __future__ import annotations

import enum

from vortosql.core.logger import Logger
from vortosql.core.model_manager.anthropic_model import (
    AnthropicChatCompletion,
    AnthropicModel,
)
from vortosql.core.model_manager.huggingface_model import (
    HuggingFaceChatCompletion,
    HuggingFaceEmbeddings,
    HuggingFaceModel,
)
from vortosql.core.model_manager.ollama_model import (
    OllamaChatCompletion,
    OllamaEmbeddings,
    OllamaModel,
)
from vortosql.core.model_manager.openai_model import (
    OpenAIChatCompletion,
    OpenAIEmbeddings,
    OpenAIModel,
)

logger = Logger(__name__)


class ModelProvider(enum.Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    ANTHROPIC = "anthropic"


class ModelType(enum.Enum):
    COMPLETION = "completion"
    EMBEDDING = "embedding"


class ModelManager:
    @classmethod
    def create_model(
        cls,
        model_provider: ModelProvider,
        model_type: ModelType,
        model_name: OpenAIModel | OllamaModel | HuggingFaceModel | AnthropicModel,
        openai_api_key: str | None = None,
        anthropic_api_key: str | None = None,
    ) -> (
        OpenAIChatCompletion
        | OpenAIEmbeddings
        | AnthropicChatCompletion
        | OllamaChatCompletion
        | OllamaEmbeddings
        | HuggingFaceChatCompletion
        | HuggingFaceEmbeddings
    ):
        if model_provider == ModelProvider.OPENAI:
            if model_type == ModelType.COMPLETION:
                return OpenAIChatCompletion(model_name, openai_api_key)
            elif model_type == ModelType.EMBEDDING:
                return OpenAIEmbeddings(model_name, openai_api_key)
        elif model_provider == ModelProvider.ANTHROPIC:
            if model_type == ModelType.COMPLETION:
                return AnthropicChatCompletion(model_name, anthropic_api_key)
        elif model_provider == ModelProvider.OLLAMA:
            if model_type == ModelType.COMPLETION:
                return OllamaChatCompletion(model_name)
            elif model_type == ModelType.EMBEDDING:
                return OllamaEmbeddings(model_name)
        elif model_provider == ModelProvider.HUGGINGFACE:
            if model_type == ModelType.COMPLETION:
                return HuggingFaceChatCompletion(model_name)
            elif model_type == ModelType.EMBEDDING:
                return HuggingFaceEmbeddings(model_name)

        logger.log(
            "error",
            "UNSUPPORTED_MODEL_COMBINATION",
            {"MODEL_PROVIDER": model_provider, "MODEL_TYPE": model_type},
        )
        raise ValueError(
            f"Unsupported combination: provider={model_provider}, type={model_type}"
        )
