import json
from typing import Dict, Any
from posthog import Posthog
from django.conf import settings
from .experiment_helper import ExperimentationClientInterface, DataSinkInterface
import logging
from datetime import datetime
logger = logging.getLogger(__name__)

_posthog_client = None

def get_posthog_client() -> Posthog:
    global _posthog_client
    if _posthog_client is None:
        _posthog_client = Posthog(
            settings.POSTHOG_API_KEY,
            host=settings.POSTHOG_HOST,
            poll_interval=30,
            personal_api_key=settings.POSTHOG_PERSONAL_API_KEY
        )
        print(_posthog_client.__dict__,"_posthog_client")
    return _posthog_client

_posthog_experimentation_client = None
_posthog_datasink_client = None

def get_posthog_experimentation_client() -> 'PosthogExperimentationClient':
    global _posthog_experimentation_client
    if _posthog_experimentation_client is None:
        _posthog_experimentation_client = PosthogExperimentationClient()
    return _posthog_experimentation_client

def get_posthog_datasink_client() -> 'PosthogDatasinkClient':
    global _posthog_datasink_client
    if _posthog_datasink_client is None:
        _posthog_datasink_client = PosthogDatasinkClient()
    return _posthog_datasink_client

class PosthogExperimentationClient(ExperimentationClientInterface):
    def __init__(self):
        self.posthog = get_posthog_client()

    def get_feature_flag_payload(self, flag_key: str, user_id: str) -> Dict[str, Any] | None:
        payload = self.posthog.get_feature_flag_payload(flag_key, distinct_id=user_id)
        if payload is not None:
            return json.loads(payload)
        return None
    
    def get_feature_flag_variant_name(self, flag_key: str, user_id: str) -> str | None:
        variant_name = self.posthog.get_feature_flag(flag_key, distinct_id=user_id)
        if variant_name is not None:
            return str(variant_name)
        return None
        

class PosthogDatasinkClient(DataSinkInterface):
    def __init__(self):
        self.posthog = get_posthog_client()

    def capture_data(self, *, flag_key: str, user_id: str, event_name: str, event_properties: Dict[str, Any], timestamp: datetime|None=None) -> None:
        variant_name = self.posthog.get_feature_flag(flag_key, distinct_id=user_id)
        properties = {
            f"$feature/{flag_key}": variant_name,
            **event_properties
        }
        self.posthog.capture(distinct_id=user_id, event=event_name, properties=properties, timestamp=timestamp) 
