import re
import typing
from datetime import datetime
import random
from string import Template
import logging
import json
import openai
from .llm_classes.LLMConfig import GLOBAL_LOADED_LLM_CONFIGS, LLMConfig
from .models import (
    LLMConfigName,
    PromptTemplate,
    ChatHistory,
    Tool,
)
from .openai_service import OpenAIService
from pydantic import BaseModel
from django.conf import settings
import posthog

from .experiment_helper.experiment_helper import ExperimentHelper

logger = logging.getLogger(__name__)


class ValidLLMConfigs:
    AzureOpenAILLMConfig = "AzureOpenAILLMConfig"

    @classmethod
    def get_all_valid_llm_configs(cls) -> list:
        return GLOBAL_LOADED_LLM_CONFIGS.keys()

    @classmethod
    def get_all_llm_configs_from_db(cls) -> list:
        return LLMConfigName.objects.all().values_list("name", flat=True)

    @classmethod
    def check_llm_configs_in_db(cls) -> bool:
        llm_configs_in_db = ValidLLMConfigs.get_all_llm_configs_from_db()
        loaded_configs = cls.get_all_valid_llm_configs()
        missing_config_names = [
            config_name
            for config_name in llm_configs_in_db
            if config_name not in loaded_configs
        ]
        if missing_config_names:
            raise ValueError(
                f"The following configs are missing from the configuration, but defined in DB: {missing_config_names} "
                f"To fix this, create these <name>.yaml files in {settings.LLM_CONFIGS_PATH} and restart the application."
            )
        return True


class ChatHistoryRepository:

    def __init__(self, chat_history_id: int | None) -> None:
        if chat_history_id is None:
            self.chat_history_obj = ChatHistory.objects.create()
        else:
            self.chat_history_obj = ChatHistory.objects.get(id=chat_history_id)

    @staticmethod
    def create_new_chat_history(*, initialize=True) -> ChatHistory:
        self_instance = ChatHistoryRepository(chat_history_id=None)
        if initialize:
            pass

    def is_chat_history_empty(self):
        return len(self.chat_history_obj.chat_history) == 0

    def commit_chat_to_db(self):
        self.chat_history_obj.save()

    @staticmethod
    def _generate_12_digit_random_id():
        min_num = 10**11
        max_num = (10**12) - 1
        return random.randint(min_num, max_num)

    def add_msgs_to_chat_history(
        self, msg_list: typing.List, timestamp: float = None, commit_to_db: bool = False
    ) -> None:
        ids = []
        if not timestamp:
            timestamp = round(datetime.now().timestamp(), 1)
        for msg in msg_list:
            msg["timestamp"] = timestamp
            id = (self._generate_12_digit_random_id(),)
            msg["id"] = id
            ids.append(id)
        self.chat_history_obj.chat_history.extend(msg_list)
        if commit_to_db:
            self.commit_chat_to_db()
        return ids

    def _add_user_msg_to_chat_history(
        self, *, msg_content: str, msg_timestamp: float
    ) -> None:
        self._add_msg_to_chat_history(
            msg_content=msg_content, msg_type="user", msg_timestamp=msg_timestamp
        )

    def get_msg_list_for_llm(self) -> list:
        msg_list = []
        for msg in self.chat_history_obj.chat_history:
            if msg["role"] in ["user", "assistant", "system"]:
                new_msg = {"content": msg["content"], "role": msg["role"]}
            elif msg["role"] == "tool":
                new_msg = {
                    "content": msg["content"],
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "name": msg["name"],
                }
            else:
                raise ValueError(f"Unexpected msg role: {msg['role']}")

            if "tool_calls" in msg:
                new_msg["tool_calls"] = msg["tool_calls"]
            msg_list.append(new_msg)
        return msg_list

    def add_or_update_system_msg(self, new_system_msg):
        if len(self.chat_history_obj.chat_history) > 0:
            if self.chat_history_obj.chat_history[0]["role"] == "system":
                self.chat_history_obj.chat_history[0]["content"] = new_system_msg
            else:
                raise ValueError(
                    f"Unexpected: First msg is not a system msg. Chat id: {self.chat_history_obj.id}"
                )
        else:
            self.chat_history_obj.chat_history = [
                {"role": "system", "content": new_system_msg}
            ]

    @staticmethod
    def get_chat_history_by_chat_id(chat_id):
        try:
            chat_history_obj = ChatHistory.objects.get(chat_id=chat_id)
            return chat_history_obj.id
        except ChatHistory.DoesNotExist:
            return None

    def get_thumbs_counts(self) -> dict:
        """
        Get counts of thumbs up (1) and thumbs down (-1) from chat history
        Returns dict with keys 'thumbs_up' and 'thumbs_down'
        """
        thumbs_up = 0
        thumbs_down = 0

        for msg in self.chat_history_obj.chat_history:
            thumb = msg.get("thumb")
            if thumb == 1:
                thumbs_up += 1
            elif thumb == -1:
                thumbs_down += 1

        return {"thumbs_up": thumbs_up, "thumbs_down": thumbs_down}

    def get_user_message_count(self) -> int:
        """
        Get count of messages where role='user' in chat history
        Returns int count of user messages
        """
        return sum(
            1 for msg in self.chat_history_obj.chat_history if msg.get("role") == "user"
        )


class LLMCommunicationWrapper:
    class LLMConfigsNotAvailable(Exception):
        def __init__(self) -> None:
            super().__init__("No LLM configs available.")

    @staticmethod
    def convert_to_function(source_code: str):
        match = re.search(r"def\s+(\w+)\s*\(", source_code)
        if match:
            function_name = match.group(1)
        else:
            raise ValueError(
                "No valid function definition found in the provided source code."
            )
        # Execute the source code in the current local scope
        exec(source_code, locals())
        # Retrieve and return the function by the extracted name
        return locals()[function_name]

    @staticmethod
    def package_function_response(was_success, response_string, timestamp=None):
        # formatted_time = get_local_time() if timestamp is None else timestamp
        packaged_message = {
            "status": "OK" if was_success else "Failed",
            "message": response_string,
            # "time": formatted_time,
        }

        return json.dumps(packaged_message, ensure_ascii=False)

    @staticmethod
    def parse_json(string) -> dict:
        """Parse JSON string into JSON with both json and demjson"""
        result = None
        try:
            result = json.loads(string, strict=True)
            return result
        except Exception as e:
            print(f"Error parsing json with json package: {e}")
            raise e

    @staticmethod
    def get_tool_context_params(tool_function_name, context_vars, context_params):
        context_params_json = {}
        for key in context_params:
            formatted_key = f'{key.strip("__")}'
            if formatted_key in context_vars:
                context_params_json[key] = context_vars[formatted_key]
            else:
                logger.error(
                    f"Key '{key}' from context_params of tool not found in context_vars"
                )
        return context_params_json

    def get_chat_history_object(self):
        return self.chat_history_repository.chat_history_obj

    def init_llm_config(self):
        if len(self.llm_config_names) == 0:
            raise LLMCommunicationWrapper.LLMConfigsNotAvailable()

        random_llm_config_name = random.choice(self.llm_config_names)

        self.llm_config_name = random_llm_config_name

        llm_config_instance: LLMConfig = GLOBAL_LOADED_LLM_CONFIGS[self.llm_config_name]
        self.llm_config_params = llm_config_instance.get_config_dict()

        if llm_config_instance.are_tools_enabled() and len(self.tool_json_specs):
            self.llm_config_params["tools"] = self.tool_json_specs

        elif len(self.tool_json_specs):
            raise ValueError(
                f"Tools not enabled in LLM config but used in LLM Prompt - {self.prompt_name}. "
                f"LLM config name - {llm_config_instance.name}"
            )

    def __init__(
        self,
        *,
        prompt_name,
        chat_history_id=None,
        assistant_id=None,
        initialize=True,
        initializing_context_vars=None,
        response_format_class: type[BaseModel] | None = None,
    ):
        self.prompt_name = prompt_name
        self.response_format_class = response_format_class
        self.prompt_template = PromptTemplate.objects.get(name=prompt_name)
        self.chat_history_repository = ChatHistoryRepository(
            chat_history_id=chat_history_id
        )

        self.tool_json_specs = [
            {"type": "function", "function": tool.tool_json_spec}
            for tool in self.prompt_template.tools.all()
        ]
        self.tool_callables = {
            tool.name: LLMCommunicationWrapper.convert_to_function(tool.tool_code)
            for tool in self.prompt_template.tools.all()
        }
        self.context_params = {
            tool.name: tool.context_params for tool in self.prompt_template.tools.all()
        }

        self.assistant_id = assistant_id

        self.llm_config_names = [
            config.name for config in self.prompt_template.llm_config_names.all()
        ]
        self.init_llm_config()

        self.to_be_logged_context_vars = self.prompt_template.logged_context_vars
        if initialize:
            if chat_history_id is not None:
                logger.error(
                    "Cannot initialize chat history if chat history is already created. Not initializing"
                )
            else:
                self.initialize_chat_history(
                    initializing_context_vars=initializing_context_vars,
                    commit_to_db=True,
                )

    def get_llm_config(self) -> dict:
        return self.llm_config_params

    def get_initial_msg_templates(self):
        return self.prompt_template.initial_messages_templates

    def initialize_chat_history(
        self, *, initializing_context_vars=None, commit_to_db=True
    ):
        if initializing_context_vars is None:
            initializing_context_vars = {}
        system_prompt = Template(
            self.prompt_template.system_prompt_template
        ).substitute(initializing_context_vars)
        init_msg_list = [{"role": "system", "content": system_prompt}]
        for msg in self.prompt_template.initial_messages_templates:
            init_msg_list.append(
                {
                    "content": Template(msg["content"]).substitute(
                        initializing_context_vars
                    ),
                    "role": msg["role"],
                    "system_generated": True,
                    "show_in_user_history": False,
                }
            )
        self.chat_history_repository.add_msgs_to_chat_history(init_msg_list)
        if commit_to_db:
            self.chat_history_repository.commit_chat_to_db()

    def handle_tool_call(self, choice_from_llm, context_vars):
        if choice_from_llm["message"].get("tool_calls") is None:
            return {}
        tool_call_message = choice_from_llm["message"]
        tool_call_instancd = tool_call_message["tool_calls"][0]
        result = tool_call_instancd["function"]
        tool_call_id = tool_call_instancd["id"]
        tool_function_name = result.get("name", None)
        if tool_function_name not in self.tool_callables:
            logger.error(
                f"Unexpected tool call - {tool_function_name}. Chat id - {self.chat_history_repository.chat_history_obj.id}"
            )
            return {}
        json_tool_function_params = result.get("arguments", {})
        tool_function_params = LLMCommunicationWrapper.parse_json(
            json_tool_function_params
        )
        context_params = self.context_params[tool_function_name]
        # Initialize context_params_json as an empty dictionary
        context_params_json = LLMCommunicationWrapper.get_tool_context_params(
            tool_function_name, context_vars, context_params
        )
        try:
            tool_output = self.tool_callables[tool_function_name](
                **context_params_json, **tool_function_params
            )
            logger.info(f"Got tool output of {tool_function_name} - {tool_output}")
            tool_output_packaged = LLMCommunicationWrapper.package_function_response(
                True, str(tool_output)
            )
            logger.info(f"Generated packaged tool response = f{tool_output_packaged}")
        except Exception as exc:
            logger.error(
                f"Error in tool call - {exc}. Chat id - {self.chat_history_repository.chat_history_obj.id}"
            )
            tool_output_packaged = LLMCommunicationWrapper.package_function_response(
                False, "Got error in tool call"
            )

        tool_call_msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [tool_call_instancd.dict()],
            "tool_call_id": tool_call_id,
        }

        our_tool_response = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_function_name,
            "content": tool_output_packaged,
        }
        existing_msg_list = self.chat_history_repository.get_msg_list_for_llm()
        new_msg_list = existing_msg_list + [tool_call_msg, our_tool_response]
        a_time = datetime.now().timestamp()
        post_tool_call_response = OpenAIService.send_messages_and_get_response(
            new_msg_list,
            self.llm_config_params,
            response_format_class=self.response_format_class,
        )
        post_tool_call_response_dict = {
            "role": "assistant",
            "message_generation_time": round(datetime.now().timestamp() - a_time, 1),
            "content": post_tool_call_response["message"]["content"],
        }
        tool_call_msg["context_params"] = context_params_json
        self.chat_history_repository.add_msgs_to_chat_history(
            [tool_call_msg, our_tool_response, post_tool_call_response_dict]
        )
        self.chat_history_repository.commit_chat_to_db()
        tool_data = {
            "used_tool": tool_function_name,
            "tool_calls": [tool_call_instancd.dict()],
            "tool_content": tool_output_packaged,
        }
        modified_message_content = {
            "type": "bot",
            "message": post_tool_call_response["message"]["content"],
            "tool_data": tool_data,
        }
        return modified_message_content

    def get_one_time_completion(self, kwargs):
        # Fetch the prompt template from the database by name
        prompt_template = PromptTemplate.objects.get(name=self.prompt_name)

        required_keys = prompt_template.required_kwargs

        # Check if all required keys are present in kwargs
        missing_keys = [
            key for key in required_keys if required_keys[key] and key not in kwargs
        ]
        if missing_keys:
            error_message = f"Missing required keys: {', '.join(missing_keys)}"
            logging.error(error_message)
            raise ValueError(error_message)

        # Access system_prompt and user_prompt fields
        system_prompt = prompt_template.system_prompt_template
        user_prompt = prompt_template.system_prompt_template

        # Substitute values in the prompts using kwargs
        formatted_system_prompt = system_prompt
        formatted_user_prompt = user_prompt

        for key, value in kwargs.items():
            formatted_system_prompt = formatted_system_prompt.replace(
                f"${key}", str(value)
            )
            formatted_user_prompt = formatted_user_prompt.replace(f"${key}", str(value))

        combined_prompt = {
            "system_prompt": formatted_system_prompt,
            "user_prompt": formatted_user_prompt,
        }

        return combined_prompt

    def get_final_user_message(self, user_msg: str, context_vars=None) -> dict:
        user_prompt = user_msg
        if self.prompt_template.user_prompt_template:
            user_prompt = Template(
                self.prompt_template.user_prompt_template
            ).substitute(**context_vars, user_msg=user_msg)
        return {"role": "user", "content": user_prompt}

    def send_user_message_and_get_response(
        self,
        user_msg: str,
        context_vars=None,
        retry_on_openai_time_limit=False,
    ) -> str:
        if context_vars is None:
            context_vars = {}
        required_keys = self.prompt_template.required_kwargs
        logged_context_vars = self.prompt_template.logged_context_vars
        missing_keys = [key for key in required_keys if key not in context_vars]
        logger.info(f"Required keys: {required_keys}. Missing keys: {missing_keys}.")
        if missing_keys:
            error_message = f"Missing required keys: {', '.join(missing_keys)}"
            raise ValueError(error_message)

        filtered_context_vars = {
            key: value
            for key, value in context_vars.items()
            if key in logged_context_vars
        }
        self.update_chat_history(context_vars)
        new_msg_list = self.chat_history_repository.get_msg_list_for_llm()
        new_msg_list += [
            self.get_final_user_message(user_msg, context_vars=context_vars)
        ]

        # The user msg is added here, but in case of tool call we are committing to db only post handling of tool
        # call. ALSO, User msg in history and the one sent to llm finally are intentionally different
        self.chat_history_repository.add_msgs_to_chat_history(
            [
                {
                    "role": "user",
                    "content": user_msg,
                    "context_vars": filtered_context_vars,
                }
            ]
        )
        a_time = datetime.now().timestamp()

        while True:
            try:
                choice_response = OpenAIService.send_messages_and_get_response(
                    messages=new_msg_list,
                    llm_config_params=self.llm_config_params,
                    response_format_class=self.response_format_class,
                )
                break
            except openai._exceptions.RateLimitError as e:
                if retry_on_openai_time_limit:
                    self.llm_config_names.remove(self.llm_config_name)
                    self.init_llm_config()
                else:
                    raise e

        if choice_response["message"].get("tool_calls") is not None:
            return self.handle_tool_call(choice_response, context_vars)
        else:
            response_msg_content = choice_response["message"]["content"]
            msg_id = self.chat_history_repository.add_msgs_to_chat_history(
                [
                    {
                        "role": "assistant",
                        "message_generation_time": round(
                            datetime.now().timestamp() - a_time, 1
                        ),
                        "content": response_msg_content,
                    }
                ]
            )[0][0]

            self.chat_history_repository.commit_chat_to_db()
            response = {"message": response_msg_content, "id": msg_id}
            return response

    def update_chat_history(self, context_vars: None):
        if context_vars is None:
            context_vars = {}
        is_chat_history_empty = self.chat_history_repository.is_chat_history_empty()
        system_prompt = Template(
            self.prompt_template.system_prompt_template
        ).substitute(**context_vars)

        if not is_chat_history_empty:
            self.chat_history_repository.add_or_update_system_msg(system_prompt)
        else:
            self.initialize_chat_history(
                initializing_context_vars=context_vars, commit_to_db=False
            )

    @staticmethod
    def update_message_thumb_rating(chat_history_obj, message_id, thumb):
        for msg in chat_history_obj.chat_history:
            if msg.get("id") and msg["id"][0] == message_id:
                msg["thumb"] = thumb
                chat_history_obj.save()
                return True
        return False

    @staticmethod
    def get_processed_chat_messages(chat_history, is_superuser):
        messages_list = []  # Initialize list to store processed messages
        mapping = {"user": "user", "assistant": "bot"}
        for i, msg in enumerate(chat_history):
            if msg.get("show_in_user_history", True) == False:
                continue
            # Check if the message role is valid and it is not a tool call or initial message
            if (
                msg["role"] in mapping
                and not msg.get("tool_calls")
                and not msg.get("initial_message", None)
            ):
                msg_type = mapping[msg["role"]]  # Map the role to its type
                message_content = msg["content"]
                try:
                    json_content = json.loads(msg["content"])
                    message_content = json_content.get("message", msg["content"])
                except:
                    message_content = msg["content"]
                extra = {}  # Initialize extra information dictionary

                # If the user is a superuser, include tool information
                if is_superuser and i > 0 and chat_history[i - 1]["role"] == "tool":
                    used_tool = chat_history[i - 1]["name"]
                    tool_calls = chat_history[i - 2].get("tool_calls", [])
                    content = chat_history[i - 1]["content"]
                    extra = {
                        "used_tool": used_tool,
                        "tool_calls": tool_calls,
                        "tool_content": content,
                    }

                # Append the message and additional information to the list
                messages_list.append(
                    {
                        "message": message_content,
                        "type": msg_type,
                        "tool_data": extra,
                        "id": msg["id"][0],
                        "thumb": msg.get("thumb", None),
                    }
                )

        return messages_list


class ABTestingLLMCommunicationWrapper(LLMCommunicationWrapper):

    def __init__(
        self,
        user_id,
        experiment_name=None,
        chat_history_id=None,
        default_prompt_template_name=None,
        initialize=True,
        initializing_context_vars=None,
        response_format_class: type[BaseModel] | None = None,
    ):
        # Take the values from the llm_config_v2 file
        self.posthog_api_key = settings.POSTHOG_API_KEY
        self.default_prompt_template_name = default_prompt_template_name
        # Initialize PostHog
        posthog.api_key = self.posthog_api_key
        posthog.host = "https://us.i.posthog.com"

        self.user_id = user_id  # Added to store user_id
        prompt_template_name = self.get_prompt_template_name_from_experiment(
            experiment_name
        )
        logger.info(f"Prompt template name from experiment: {prompt_template_name}")
        try:
            super().__init__(
                prompt_name=prompt_template_name,
                chat_history_id=chat_history_id,
                initialize=initialize,
                initializing_context_vars=initializing_context_vars,
                response_format_class=response_format_class,
            )
        except PromptTemplate.DoesNotExist:
            logger.error(
                f"Prompt template from experimentation does not exist. Prompt name: {prompt_template_name}"
            )
            super().__init__(
                prompt_name=default_prompt_template_name,
                chat_history_id=chat_history_id,
                initialize=initialize,
                initializing_context_vars=initializing_context_vars,
                response_format_class=response_format_class,
            )

    def get_prompt_template_name_from_experiment(self, experiment_name):
        try:
            # Fetch the feature flag value for the user
            feature_flag_variant_name = (
                ExperimentHelper().get_feature_flag_variant_name(
                    flag_key=experiment_name, user_id=self.user_id
                )
            )
            if not feature_flag_variant_name:
                logging.error(
                    f"Feature flag was returned None. User id: {self.user_id}, experiment name: {experiment_name}"
                )
                return self.default_prompt_template_name

            return feature_flag_variant_name
        except Exception as e:
            logging.error(f"Error determining experiment group from feature flag: {e}")
            return self.default_prompt_template_name
