import enum
import time
from typing import Union, List, Dict

import tiktoken
from openai import OpenAI

from nl2sql_data_agent.core.logger import Logger

logger = Logger(__name__)


class OpenAIModel(enum.Enum):
    ## Completion Models
    # GPT-5.4 family
    GPT_54 = "gpt-5.4"
    GPT_54_PRO = "gpt-5.4-pro"
    GPT_54_MINI = "gpt-5.4-mini"
    GPT_54_NANO = "gpt-5.4-nano"

    # GPT-5 family
    GPT_5 = "gpt-5"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5_NANO = "gpt-5-nano"

    # GPT-4.x
    GPT_4_1 = "gpt-4.1"

    ## Embeddings Models
    TEXT_EMBEDDING_3_LARGE = "text-embedding-3-large"
    TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"


class OpenAIChatCompletion:
    def __init__(
        self,
        model_name: OpenAIModel,
        openai_api_key: str,
    ):
        self.model = model_name.value
        self.client = OpenAIUtils.get_openai_client(openai_api_key=openai_api_key)

    def get_chat_completion(
        self,
        messages: List[Dict[str, str]],
        frequency_penalty=None,
        logit_bias=None,
        logprobs=None,
        top_logprobs=None,
        max_tokens=None,
        n=None,
        presence_penalty=None,
        response_format=None,
        seed=None,
        stop=None,
        stream=None,
        temperature=None,
        top_p=None,
        tools=None,
        tool_choice=None,
        user=None,
    ):
        payload = {"model": self.model, "messages": messages}
        optional_params = {
            "frequency_penalty": frequency_penalty,
            "logit_bias": logit_bias,
            "logprobs": logprobs,
            "top_logprobs": top_logprobs,
            "max_tokens": max_tokens,
            "n": n,
            "presence_penalty": presence_penalty,
            "response_format": response_format,
            "seed": seed,
            "stop": stop,
            "stream": stream,
            "temperature": temperature,
            "top_p": top_p,
            "tools": tools,
            "tool_choice": tool_choice,
            "user": user,
        }
        for key, value in optional_params.items():
            if value is not None:
                payload[key] = value

        try:
            start_time = time.time()
            response = self.client.chat.completions.create(**payload)
            end_time = time.time()
            completion_content = [choice.message.content for choice in response.choices]
            return {
                "completion_content": completion_content,
                "completion_latency": end_time - start_time,
                "num_input_tokens": response.usage.prompt_tokens,
                "num_output_tokens": response.usage.completion_tokens,
            }
        except Exception as e:
            logger.log(
                "error",
                "CHAT_COMPLETION_FAILED",
                {"OPENAI_MODEL": self.model, "payload": payload, "error": str(e)},
            )
            raise


class OpenAIEmbeddings:
    def __init__(
        self,
        model_name: OpenAIModel,
        openai_api_key: str,
    ):
        self.model = model_name.value
        self.client = OpenAIUtils.get_openai_client(openai_api_key=openai_api_key)

    def get_embedding(
        self,
        input_data: Union[str, List],
        encoding_format=None,
        dimensions=None,
        user=None,
    ):
        payload = {"model": self.model, "input": input_data}
        optional_params = {
            "encoding_format": encoding_format,
            "dimensions": dimensions,
            "user": user,
        }
        for key, value in optional_params.items():
            if value is not None:
                payload[key] = value

        try:
            response = self.client.embeddings.create(**payload)
            if isinstance(input_data, list):
                return [item.embedding for item in response.data]
            return response.data[0].embedding
        except Exception as e:
            logger.log(
                "error",
                "EMBEDDING_FAILED",
                {"OPENAI_MODEL": self.model, "payload": payload, "error": str(e)},
            )
            raise


class OpenAIUtils:
    @staticmethod
    def get_openai_client(openai_api_key: str):
        """Set up the OpenAI client."""
        return OpenAI(api_key=openai_api_key)

    @staticmethod
    def num_tokens_from_messages(messages, model: str):
        """Return the number of tokens used by a list of messages."""
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            logger.log(
                "WARNING",
                "MODEL_NOT_FOUND",
                {"model": model, "message": "Using cl100k_base encoding."},
            )
            encoding = tiktoken.get_encoding("cl100k_base")
        # gpt-3.5-turbo-0301 had a different overhead; all modern models use 3/1
        if model == "gpt-3.5-turbo-0301":
            tokens_per_message = 4
            tokens_per_name = -1
        else:
            tokens_per_message = 3
            tokens_per_name = 1
        num_tokens = 0
        for message in messages:
            num_tokens += tokens_per_message
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":
                    num_tokens += tokens_per_name
        num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
        return num_tokens

    @staticmethod
    def get_num_text_tokens(text: str, model: str) -> int:
        """Returns the number of tokens in a text string."""
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            logger.log(
                "WARNING",
                "MODEL_NOT_FOUND",
                {"model": model, "message": "Using cl100k_base encoding."},
            )
            encoding = tiktoken.get_encoding("cl100k_base")
        num_tokens = len(encoding.encode(text))
        return num_tokens
