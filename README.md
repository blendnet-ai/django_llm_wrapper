

## Example Workflow

1. **Configuration**: Add YAML files for all required LLM configurations and populate the `LLMConfigName` table.
2. **Define Prompt Templates**: Create entries in the `PromptTemplate` table.
3. **Defining a function tool** (optional): Create entries in the `Tool` table.
4. **Initialize Wrapper**: Instantiate the `LLMCommunicationWrapper` or `ABTestingLLMCommunicationWrapper`.
5. **Send Messages**: Use `send_user_message_and_get_response` to interact with the LLM.

---
## Models Overview

### **Tool**
Enable function calling (as defined [here](https://platform.openai.com/docs/guides/function-calling))

- **Fields**:
  - `updated_at`, `created_at`: Timestamps.
  - `tool_code`
  - `default_values_for_non_llm_params`
  - `tool_json_spec`: Filled automatically when added from admin form.
  - `name`: Name of the tool.
  - `context_params`

---

### **LLMConfigName**
Manages the configuration names of different LLMs.

- **Fields**:
  - `name`: Primary key and the name of the LLM configuration.

---

### **PromptTemplate**
Manages prompt templates used for LLM communication.

- **Fields**:
  - `name`: Name of the prompt template.
  - `llm_config_names`: Many-to-many relationship with `LLMConfigName`.
  - `required_kwargs`: Keywords that must be passed in the system prompt.
  - `initial_messages_templates`: Initial messages in JSON format.
  - `system_prompt_template`: System-level prompt.
  - `user_prompt_template`: User-level prompt.
  - `logged_context_vars`: Context vars to be included in chat history.
  - `tools`: Many-to-many relationship with `Tool`.

---

### **ChatHistory**
Tracks the history of chats.

- **Fields**:
  - `updated_at`, `created_at`: Timestamps.
  - `chat_history`: JSON field to store chat history.
  - `current_context_variables`

---

## Configuration

### **YAML Configuration**
1. Create a folder in your project to store YAML files (e.g., `/path/to/llm_configs/`).
2. Each YAML file should define the credentials and configurations for an LLM. Example structure for Azure:

    ```yaml
    name: "gpt-4-32k-azure"
    llm_config_class: "AzureOpenAILLMConfig"
    endpoint: "https://example.com"
    deployment_name: "gpt-4"
    api_key: "your_api_key"
    api_version: "2024-01-01"
    tools_enabled: true
    ```
3. Options for `llm_config_class`:
 - "AzureOpenAILLMConfig": Use for Azure-based OpenAI LLM configurations.
 - "GeminiConfig": Use for Gemini LLM configurations.
 - "AnthropicConfig": Use for Anthropic LLM configurations.
 - "GroqConfig": Use for Groq LLM configurations.
4. Ensure the file name matches the `name` field, e.g., `gpt-4-32k-azure.yml`.
5. Set the `LLM_CONFIGS_PATH` in your settings to point to the folder containing YAML files:

    ```python
    LLM_CONFIGS_PATH = "/path/to/llm_configs/"
    ```

6. Populate the `LLMConfigName` table with the names of the YAML configurations.

---

## Defining a Prompt Template

To define a new prompt template:

1. Add a row to the `PromptTemplate` table with the following details:
   - `name`: Unique name for the template.
   - `llm_config_names`: Select the LLM configurations to use (selected randomly on llm wrapper instance creation)
   - `required_kwargs`: List the required keys for the prompt (e.g., `["question", "context"]`).
   - `initial_messages_templates`: Define initial messages in the format:

     ```json
     [{"role": "assistant", "content": "Hello! How can I help you today?"}]
     ```

   - `system_prompt_template`: Template text for the system-level prompt.
   - `user_prompt_template`: Template text for user-specific prompts.
   - `logged_context_vars`: Defined context vars which needs to be logged in chat history.

---

## Defining a function tool

1. Go to the admin form for tool (`/admin/llm_wrapper/tool/add/`)
2. Fill the values
3. Associate tool with `PromptTemplate`

---


## Using the LLM Wrapper

### **Initialization**
1. Import the wrapper:

    ```python
    from your_app_name.repositories import LLMCommunicationWrapper
    ```
    or
   ```python
   from your_app_name.repositories import ABTestingLLMCommunicationWrapper
   ```

3. Create an instance of the wrapper:
### Without PostHog template selection:
   - **Example 1**: Initialize a new chat session:

     ```python
     llm_wrapper = LLMCommunicationWrapper(
         prompt_name="prompt_template_name",
         chat_history_id=None,
         initialize=True,
         initializing_context_vars={"question": "Print something in Python"},
         response_format_class=Response,
     )
     ```

   - **Example 2**: Use an existing chat history:

     ```python
     llm_wrapper = LLMCommunicationWrapper(
         prompt_name="prompt_template_name",
         chat_history_id=6,
         initialize=False,
         initializing_context_vars={"question": "Find sum of digits of the given number"},
         response_format_class=Response,
     )
     ```
- `prompt_name`: Name of prompt template.
- `chat_history_id`: `id` from `ChatHistory` table.
- `initialize`: boolean to create a new `ChatHistory` row.
- `initializing_context_vars`: Intial context vars.
- `response_format_class` (if supported by the model)

### With PostHog template selection:
  ```python
    llm_wrapper = ABTestingLLMCommunicationWrapper(
      user_id=1,
      experiment_name="your_experiment_name",
      default_prompt_template_name="prompt_template_name",
      chat_history_id=6,
      initialize=False,
      initializing_context_vars={"question": "Find sum of digits"},
      response_format_class=Response,
    )
  ```
- `user_id`
- `experiment_name`: Experiment name from PostHog.
- `default_prompt_template_name`: Used if prompt template name could not be determined through PostHog. 

---

### **Sending Messages**

Use the `send_user_message_and_get_response` method to send a message and get a response.

- **Parameters**:
  - `message`: The user’s message.
  - `context_vars`: Context variables to update the prompt.
  - `retry_on_openai_time_limit`: Retry with a different LLM config on openai time limit when set as True.

- **Example Usage**:

    ```python
    response_text = llm_wrapper.send_user_message_and_get_response(
        "Is my solution correct so far?",
        {"question": "Find sum of digits"},
        retry_on_openai_time_limit=True
    )
    print(response_text)
    ```

---


