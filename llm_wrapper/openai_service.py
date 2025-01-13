from openai import AzureOpenAI
import time
from openai.types.beta.assistant import Assistant
from openai.types.beta.thread import Thread
from openai.types import FileObject
from openai.types.beta.threads.run import Run
from pydantic import BaseModel
import logging
import litellm


class OpenAIService:
    @staticmethod
    def send_messages_and_get_response(
        messages: list,
        llm_config_params: dict,
        response_format_class: type[BaseModel] | None = None,
    ):
        response = litellm.completion(
            **llm_config_params,
            messages=messages,
            response_format=response_format_class
        )
        return response["choices"][0]
