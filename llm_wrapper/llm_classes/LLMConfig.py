import abc
import os
import yaml
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

class LLMConfig:
    def __init__(self, name:str, tools_enabled:bool=False):
        self.name = name
        self.tools_enabled = tools_enabled

    def are_tools_enabled(self):
        return self.tools_enabled

    @classmethod
    def load_configs(cls, directory=settings.LLM_CONFIGS_PATH):
        configs = {}
        for filename in os.listdir(directory):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                with open(os.path.join(directory, filename), 'r') as file:
                    config = yaml.safe_load(file)
                    name = config.get('name')
                    llm_config_class = config.pop('llm_config_class')
                    if not name or not type:
                        raise ImproperlyConfigured(f"Invalid configuration in {filename}")
                    llm_class = cls.get_llm_class(llm_config_class)
                    llm_instance = llm_class(**config)
                    configs[name] = llm_instance
        return configs

    @staticmethod
    def get_llm_class(name):
        """Return the appropriate LLMConfig subclass based on type."""
        if name == 'AzureOpenAILLMConfig':
            return AzureOpenAILLMConfig
        elif name == 'GeminiConfig':
            return GeminiConfig
        elif name=='AnthropicConfig':
            return AnthropicConfig
        elif name=='GroqConfig':
            return GroqConfig
        elif name=='OpenAIAssistantConfig':
            return OpenAIAssistantConfig
        else:
            raise ImproperlyConfigured(f"Unsupported LLMConfig type: {name}")

    @abc.abstractmethod
    def get_config_dict(self):
        raise NotImplementedError

class AzureOpenAILLMConfig(LLMConfig):
    def __init__(self, **kwargs):
        super().__init__(kwargs.get("name"), tools_enabled=kwargs.get("tools_enabled"))
        errors = []
        required_params = {"endpoint":str, "deployment_name":str, "api_key":str, "api_version":str}
        for param, rp_type in required_params.items():
            if param not in kwargs or rp_type != type(kwargs.get(param)):
                errors.append(f"{param} is required and must be a {rp_type}")
        if errors:
            raise ImproperlyConfigured(", ".join(errors))
        self.name=kwargs.get("name")
        self.endpoint =kwargs.get("endpoint")
        self.deployment_name =kwargs.get("deployment_name")
        self.api_key = kwargs.get("api_key")
        self.api_version = kwargs.get("api_version")
    
    def get_config_dict(self):
        return {
            "api_base":self.endpoint,
            "model":f"azure/{self.deployment_name}",
            "api_key":self.api_key,
            "api_version":self.api_version
        }
    
class GeminiConfig(LLMConfig):
    def __init__(self, **kwargs):
        super().__init__(kwargs.get("name"), tools_enabled=kwargs.get("tools_enabled", False))
        errors = []
        required_params = {"model_name": str, "api_key": str,"endpoint": str}
        
        # Check required parameters
        for param, rp_type in required_params.items():
            if param not in kwargs or rp_type != type(kwargs.get(param)):
                errors.append(f"{param} is required and must be a {rp_type}")
        
        if errors:
            raise ImproperlyConfigured(", ".join(errors))
        
        self.name = kwargs.get("name")
        self.endpoint =kwargs.get("endpoint")
        self.model_name = kwargs.get("model_name")
        self.api_key = kwargs.get("api_key")

    def get_config_dict(self):
        return {
            "model": f"gemini/{self.model_name}",
            "api_key": self.api_key
        }
    
class AnthropicConfig(LLMConfig):
    def __init__(self, **kwargs):
        super().__init__(kwargs.get("name"), tools_enabled=kwargs.get("tools_enabled", False))
        errors = []
        required_params = {"model_name": str, "api_key": str}
        
        # Check required parameters
        for param, rp_type in required_params.items():
            if param not in kwargs or rp_type != type(kwargs.get(param)):
                errors.append(f"{param} is required and must be a {rp_type}")
        
        if errors:
            raise ImproperlyConfigured(", ".join(errors))
        
        self.name = kwargs.get("name")
        self.model_name = kwargs.get("model_name")
        self.api_key = kwargs.get("api_key")

    def get_config_dict(self):
        return {
            "model": f"anthropic/{self.model_name}",
            "api_key": self.api_key
        }

class GroqConfig(LLMConfig):
    def __init__(self, **kwargs):
        super().__init__(kwargs.get("name"), tools_enabled=kwargs.get("tools_enabled", False))
        errors = []
        required_params = {"model_name": str, "api_key": str}
        
        # Check required parameters
        for param, rp_type in required_params.items():
            if param not in kwargs or rp_type != type(kwargs.get(param)):
                errors.append(f"{param} is required and must be a {rp_type}")
        
        if errors:
            raise ImproperlyConfigured(", ".join(errors))
        
        self.name = kwargs.get("name")
        self.model_name = kwargs.get("model_name")
        self.api_key = kwargs.get("api_key")

    def get_config_dict(self):
        return {
            "model": f"groq/{self.model_name}",
            "api_key": self.api_key
        }

class OpenAIAssistantConfig(LLMConfig):
    def __init__(self, **kwargs):
        super().__init__(kwargs.get("name"), tools_enabled=kwargs.get("tools_enabled", False))
        errors = []
        required_params = {"model_name": str, "api_key": str}
        
        # Check required parameters
        for param, rp_type in required_params.items():
            if param not in kwargs or rp_type != type(kwargs.get(param)):
                errors.append(f"{param} is required and must be a {rp_type}")
        
        if errors:
            raise ImproperlyConfigured(", ".join(errors))
        
        self.name = kwargs.get("name")
        self.model_name = kwargs.get("model_name")
        self.api_key = kwargs.get("api_key")

    def get_config_dict(self):
        return {
            "model": f"openai/{self.model_name}",
            "api_key": self.api_key
        }
GLOBAL_LOADED_LLM_CONFIGS = LLMConfig.load_configs()
