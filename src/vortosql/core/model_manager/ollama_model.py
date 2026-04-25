import enum
import time

import ollama

from vortosql.core.logger import Logger

logger = Logger(__name__)


class OllamaModel(enum.Enum):
    # https://ollama.com/library?sort=popular

    # Chat Models
    LLAM3_1_8B = "llama3.1:8b", 128256
    LLAM3_1_8B_INSTRUCT_Q4_0 = "llama3.1:8b-instruct-q4_0", 128256
    LLAM3_1_8B_INSTRUCT_Q8_0 = "llama3.1:8b-instruct-q8_0", 128256
    LLAM3_1_70B = "llama3.1:70b", 128256

    MISTRAL_7B = "mistral:7b", None

    # Embeddings Models
    NOMIC_EMBED_TEXT_LATEST = "nomic-embed-text:latest", None
    NOMIC_EMBED_TEXT_V1_5 = "nomic-embed-text:v1.5", None
    MXBAI_EMBED_LARGE_LATEST = "mxbai-embed-large:latest", None
    MXBAI_EMBED_LARGE_335M = "mxbai-embed-large:335m", None

    @property
    def value(self):
        return self._value_[0]

    def get_num_ctx(self):
        return self._value_[1]


class OllamaChatCompletion:
    def __init__(self, model_name: OllamaModel):
        self.num_ctx = model_name.get_num_ctx()  # may be None
        self.model = model_name.value

    def get_chat_completion(
        self, messages: list, temperature: float | None = None, n: int = 1, **kwargs
    ):
        payload = {"model": self.model, "messages": messages}
        if self.num_ctx is not None:
            payload["options"] = {"num_ctx": self.num_ctx}
        if temperature is not None:
            payload.setdefault("options", {})["temperature"] = temperature
        try:
            results = {
                "completion_content": n * [None],
                "completion_latency": 0,
                "num_input_tokens": 0,
                "num_output_tokens": 0,
            }
            for i in range(n):
                start_time = time.time()
                response = ollama.chat(**payload)
                end_time = time.time()

                results["completion_content"][i] = response.message.content
                results["completion_latency"] += end_time - start_time
                results["num_input_tokens"] += response.prompt_eval_count
                results["num_output_tokens"] += response.eval_count
            return results

        except Exception as e:
            logger.log(
                "error",
                "CHAT_COMPLETION_FAILED",
                {"OLLAMA_MODEL": self.model, "payload": payload, "error": str(e)},
            )
            raise


class OllamaEmbeddings:
    def __init__(self, model_name: OllamaModel):
        self.model = model_name.value

    def get_embedding(self, input_data: str):
        payload = {"model": self.model, "input": input_data}
        try:
            response = ollama.embed(**payload)
            return response.embeddings[0]
        except Exception as e:
            logger.log(
                "error",
                "EMBEDDING_FAILED",
                {"OLLAMA_MODEL": self.model, "payload": payload, "error": str(e)},
            )
            raise
