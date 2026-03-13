"""Custom model provider that wraps BedrockModel with logging."""

import logging

from strands.models.bedrock import BedrockModel

logger = logging.getLogger(__name__)


class LoggingBedrockModel(BedrockModel):
    """BedrockModel wrapper that logs all stream() calls.

    Demonstrates the custom provider pattern - any class that implements
    the Strands Model interface can be used with CustomProviderConfig.
    """

    def __init__(self, model_id: str, **kwargs):
        logger.info(f"[CustomProvider] Initializing LoggingBedrockModel: {model_id}")
        super().__init__(model_id=model_id, **kwargs)

    async def stream(self, *args, **kwargs):
        logger.info("[CustomProvider] stream() called")
        async for event in super().stream(*args, **kwargs):
            yield event
        logger.info("[CustomProvider] stream() completed")
