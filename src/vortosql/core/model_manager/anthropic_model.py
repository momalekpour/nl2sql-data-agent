import enum
import time
from typing import Dict, List

import anthropic

from vortosql.core.logger import Logger

logger = Logger(__name__)


class AnthropicModel(enum.Enum):
    # Claude 4.x
    CLAUDE_OPUS_4_6 = "claude-opus-4-6"
    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5-20251001"

    # Claude 3.x
    CLAUDE_3_5_SONNET = "claude-3-5-sonnet-20241022"
    CLAUDE_3_5_HAIKU = "claude-3-5-haiku-20241022"
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"


class AnthropicChatCompletion:
    def __init__(
        self,
        model_name: AnthropicModel,
        anthropic_api_key: str,
    ):
        self.model = model_name.value
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)

    def get_chat_completion(
        self,
        messages: List[Dict[str, str]],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature=None,
        top_p=None,
        top_k=None,
        stop_sequences=None,
    ):
        # Anthropic requires system to be passed separately, not in messages
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        optional_params = {
            "system": system,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "stop_sequences": stop_sequences,
        }
        for key, value in optional_params.items():
            if value is not None:
                payload[key] = value

        try:
            start_time = time.time()
            response = self.client.messages.create(**payload)
            end_time = time.time()
            completion_content = [
                block.text for block in response.content if hasattr(block, "text")
            ]
            return {
                "completion_content": completion_content,
                "completion_latency": end_time - start_time,
                "num_input_tokens": response.usage.input_tokens,
                "num_output_tokens": response.usage.output_tokens,
            }
        except Exception as e:
            logger.log(
                "error",
                "CHAT_COMPLETION_FAILED",
                {"ANTHROPIC_MODEL": self.model, "payload": payload, "error": str(e)},
            )
            raise
