from django.apps import AppConfig
from django.conf import settings


class OpenAIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "llm_wrapper"

    def ready(self) -> None:
        from llm_wrapper.repositories import ValidLLMConfigs

        if not settings.DISABLE_PROMPT_VALIDATIONS:
            ValidLLMConfigs.check_llm_configs_in_db()
