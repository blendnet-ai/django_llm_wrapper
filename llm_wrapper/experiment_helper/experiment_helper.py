from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)

class ExperimentationClientInterface(ABC):
    @abstractmethod
    def get_feature_flag_payload(self, flag_key: str, user_id: str) -> Dict[str, Any] | None:
        pass
    
    @abstractmethod
    def get_feature_flag_variant_name(self, flag_key: str, user_id: str) -> str | None:
        pass

class DataSinkInterface(ABC):
    @abstractmethod
    def capture_data(self, *, flag_key: str, user_id: str, event_name: str, event_properties: Dict[str, Any], timestamp: datetime|None=None) -> None:
        pass

class ExperimentHelper:
    def __init__(
        self,
        experimentation_client: Optional[ExperimentationClientInterface] = None,
        data_sink_client: Optional[DataSinkInterface] = None
    ):
        # Import here to avoid circular imports
        from .posthog_clients import get_posthog_experimentation_client, get_posthog_datasink_client
        
        self.experimentation_client = experimentation_client or get_posthog_experimentation_client()
        self.data_sink_client = data_sink_client or get_posthog_datasink_client()

    def get_feature_flag_payload(self, *, flag_key: str, user_id: str) -> Dict[str, Any]:
        payload = self.experimentation_client.get_feature_flag_payload(flag_key, user_id)
        if payload is None:
            logger.error(f"Feature flag payload not found for {flag_key} and user {user_id}")
            return {}
        return payload
    
    def get_feature_flag_variant_name(self, *, flag_key: str, user_id: str) -> str | None:
        variant_name = self.experimentation_client.get_feature_flag_variant_name(flag_key, user_id)
        if variant_name is None:
            logger.error(f"Feature flag payload not found for {flag_key} and user {user_id}")
            return None
        return variant_name

    def capture_data(
        self,
        *,
        flag_key: str,
        user_id: str,
        event_name: str,
        event_properties: Dict[str, Any],
        timestamp: datetime|None=None
    ) -> None:
        event_properties["env"] = settings.ENV
        self.data_sink_client.capture_data(flag_key=flag_key, user_id=user_id, event_name=event_name, event_properties=event_properties, timestamp=timestamp)
