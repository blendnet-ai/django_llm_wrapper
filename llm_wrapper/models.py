from django.db import models


class Tool(models.Model):
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    tool_code = models.TextField()
    default_values_for_non_llm_params = models.JSONField(default=dict, blank=True)
    tool_json_spec = models.JSONField(default=dict, blank=True)
    name = models.CharField(max_length=100)
    context_params = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name


class LLMConfigName(models.Model):
    name = models.CharField(max_length=100, primary_key=True)


class PromptTemplate(models.Model):

    name = models.CharField(max_length=100)
    llm_config_names = models.ManyToManyField(LLMConfigName, blank=True)
    required_kwargs = models.JSONField(
        blank=True,
        default=list,
        help_text="Required key words to be passed in user prompt template. If not provided by calling code, error will be raised. AS OF NOW, ERROR IS RAISED IF ANY KEYWORD IS MISSED, SINCE OTHERWISE $TEMPLATE_VAR LIKE THING WILL REMAIN IN PROMPT. FOR REQUIRED_KEYWORD ARGUMENTS FUNCTIONALITY, WE NEED DEFAULT VALUES OF OPTIONAL ARGS. CHECK IF THIS IS NEEDED, OR REMOVE REQUIRED KWARGS FIELD FROM HERE.",
    )
    initial_messages_templates = models.JSONField(
        blank=True,
        default=list,
        help_text="Initial msgs in the format [{'role': 'assistant|user', 'content': '...'}]",
    )
    system_prompt_template = models.TextField()
    user_prompt_template = models.TextField(blank=True, default="")
    logged_context_vars = models.JSONField(
        blank=True,
        default=list,
        help_text="Context variables to be logged in the chat log along with each user message, for later analysis.",
    )
    tools = models.ManyToManyField(Tool, blank=True)


class ChatHistory(models.Model):
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    chat_history = models.JSONField(default=list)
    current_context_variables = models.JSONField(default=dict)
