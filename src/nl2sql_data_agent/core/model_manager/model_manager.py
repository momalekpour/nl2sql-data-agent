import enum
from typing import Union

from nl2sql_data_agent.core.logger import Logger
from nl2sql_data_agent.core.model_manager.anthropic_model import (
    AnthropicModel,
    AnthropicChatCompletion,
)
from nl2sql_data_agent.core.model_manager.ollama_model import (
    OllamaModel,
    OllamaChatCompletion,
    OllamaEmbeddings,
)
from nl2sql_data_agent.core.model_manager.openai_model import (
    OpenAIModel,
    OpenAIChatCompletion,
    OpenAIEmbeddings,
)
from nl2sql_data_agent.core.model_manager.huggingface_model import (
    HuggingFaceModel,
    HuggingFaceChatCompletion,
    HuggingFaceEmbeddings,
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
        model_name: Union[OpenAIModel, OllamaModel, HuggingFaceModel, AnthropicModel],
        openai_api_key: str | None = None,
        anthropic_api_key: str | None = None,
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
