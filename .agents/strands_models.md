Directory structure:
└── models/
    ├── __init__.py
    ├── anthropic.py
    ├── bedrock.py
    ├── litellm.py
    ├── llamaapi.py
    ├── mistral.py
    ├── model.py
    ├── ollama.py
    ├── openai.py
    ├── sagemaker.py
    └── writer.py


Files Content:

================================================
FILE: src/strands/models/__init__.py
================================================
"""SDK model providers.

This package includes an abstract base Model class along with concrete implementations for specific providers.
"""

from . import bedrock, model
from .bedrock import BedrockModel
from .model import Model

__all__ = ["bedrock", "model", "BedrockModel", "Model"]



================================================
FILE: src/strands/models/anthropic.py
================================================
"""Anthropic Claude model provider.

- Docs: https://docs.anthropic.com/claude/reference/getting-started-with-the-api
"""

import base64
import json
import logging
import mimetypes
from typing import Any, AsyncGenerator, Optional, Type, TypedDict, TypeVar, Union, cast

import anthropic
from pydantic import BaseModel
from typing_extensions import Required, Unpack, override

from ..event_loop.streaming import process_stream
from ..tools import convert_pydantic_to_tool_spec
from ..types.content import ContentBlock, Messages
from ..types.exceptions import ContextWindowOverflowException, ModelThrottledException
from ..types.streaming import StreamEvent
from ..types.tools import ToolSpec
from .model import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AnthropicModel(Model):
    """Anthropic model provider implementation."""

    EVENT_TYPES = {
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_stop",
    }

    OVERFLOW_MESSAGES = {
        "input is too long",
        "input length exceeds context window",
        "input and output tokens exceed your context limit",
    }

    class AnthropicConfig(TypedDict, total=False):
        """Configuration options for Anthropic models.

        Attributes:
            max_tokens: Maximum number of tokens to generate.
            model_id: Calude model ID (e.g., "claude-3-7-sonnet-latest").
                For a complete list of supported models, see
                https://docs.anthropic.com/en/docs/about-claude/models/all-models.
            params: Additional model parameters (e.g., temperature).
                For a complete list of supported parameters, see https://docs.anthropic.com/en/api/messages.
        """

        max_tokens: Required[int]
        model_id: Required[str]
        params: Optional[dict[str, Any]]

    def __init__(self, *, client_args: Optional[dict[str, Any]] = None, **model_config: Unpack[AnthropicConfig]):
        """Initialize provider instance.

        Args:
            client_args: Arguments for the underlying Anthropic client (e.g., api_key).
                For a complete list of supported arguments, see https://docs.anthropic.com/en/api/client-sdks.
            **model_config: Configuration options for the Anthropic model.
        """
        self.config = AnthropicModel.AnthropicConfig(**model_config)

        logger.debug("config=<%s> | initializing", self.config)

        client_args = client_args or {}
        self.client = anthropic.AsyncAnthropic(**client_args)

    @override
    def update_config(self, **model_config: Unpack[AnthropicConfig]) -> None:  # type: ignore[override]
        """Update the Anthropic model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> AnthropicConfig:
        """Get the Anthropic model configuration.

        Returns:
            The Anthropic model configuration.
        """
        return self.config

    def _format_request_message_content(self, content: ContentBlock) -> dict[str, Any]:
        """Format an Anthropic content block.

        Args:
            content: Message content.

        Returns:
            Anthropic formatted content block.

        Raises:
            TypeError: If the content block type cannot be converted to an Anthropic-compatible format.
        """
        if "document" in content:
            mime_type = mimetypes.types_map.get(f".{content['document']['format']}", "application/octet-stream")
            return {
                "source": {
                    "data": (
                        content["document"]["source"]["bytes"].decode("utf-8")
                        if mime_type == "text/plain"
                        else base64.b64encode(content["document"]["source"]["bytes"]).decode("utf-8")
                    ),
                    "media_type": mime_type,
                    "type": "text" if mime_type == "text/plain" else "base64",
                },
                "title": content["document"]["name"],
                "type": "document",
            }

        if "image" in content:
            return {
                "source": {
                    "data": base64.b64encode(content["image"]["source"]["bytes"]).decode("utf-8"),
                    "media_type": mimetypes.types_map.get(f".{content['image']['format']}", "application/octet-stream"),
                    "type": "base64",
                },
                "type": "image",
            }

        if "reasoningContent" in content:
            return {
                "signature": content["reasoningContent"]["reasoningText"]["signature"],
                "thinking": content["reasoningContent"]["reasoningText"]["text"],
                "type": "thinking",
            }

        if "text" in content:
            return {"text": content["text"], "type": "text"}

        if "toolUse" in content:
            return {
                "id": content["toolUse"]["toolUseId"],
                "input": content["toolUse"]["input"],
                "name": content["toolUse"]["name"],
                "type": "tool_use",
            }

        if "toolResult" in content:
            return {
                "content": [
                    self._format_request_message_content(
                        {"text": json.dumps(tool_result_content["json"])}
                        if "json" in tool_result_content
                        else cast(ContentBlock, tool_result_content)
                    )
                    for tool_result_content in content["toolResult"]["content"]
                ],
                "is_error": content["toolResult"]["status"] == "error",
                "tool_use_id": content["toolResult"]["toolUseId"],
                "type": "tool_result",
            }

        raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

    def _format_request_messages(self, messages: Messages) -> list[dict[str, Any]]:
        """Format an Anthropic messages array.

        Args:
            messages: List of message objects to be processed by the model.

        Returns:
            An Anthropic messages array.
        """
        formatted_messages = []

        for message in messages:
            formatted_contents: list[dict[str, Any]] = []

            for content in message["content"]:
                if "cachePoint" in content:
                    formatted_contents[-1]["cache_control"] = {"type": "ephemeral"}
                    continue

                formatted_contents.append(self._format_request_message_content(content))

            if formatted_contents:
                formatted_messages.append({"content": formatted_contents, "role": message["role"]})

        return formatted_messages

    def format_request(
        self, messages: Messages, tool_specs: Optional[list[ToolSpec]] = None, system_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        """Format an Anthropic streaming request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An Anthropic streaming request.

        Raises:
            TypeError: If a message contains a content block type that cannot be converted to an Anthropic-compatible
                format.
        """
        return {
            "max_tokens": self.config["max_tokens"],
            "messages": self._format_request_messages(messages),
            "model": self.config["model_id"],
            "tools": [
                {
                    "name": tool_spec["name"],
                    "description": tool_spec["description"],
                    "input_schema": tool_spec["inputSchema"]["json"],
                }
                for tool_spec in tool_specs or []
            ],
            **({"system": system_prompt} if system_prompt else {}),
            **(self.config.get("params") or {}),
        }

    def format_chunk(self, event: dict[str, Any]) -> StreamEvent:
        """Format the Anthropic response events into standardized message chunks.

        Args:
            event: A response event from the Anthropic model.

        Returns:
            The formatted chunk.

        Raises:
            RuntimeError: If chunk_type is not recognized.
                This error should never be encountered as we control chunk_type in the stream method.
        """
        match event["type"]:
            case "message_start":
                return {"messageStart": {"role": "assistant"}}

            case "content_block_start":
                content = event["content_block"]

                if content["type"] == "tool_use":
                    return {
                        "contentBlockStart": {
                            "contentBlockIndex": event["index"],
                            "start": {
                                "toolUse": {
                                    "name": content["name"],
                                    "toolUseId": content["id"],
                                }
                            },
                        }
                    }

                return {"contentBlockStart": {"contentBlockIndex": event["index"], "start": {}}}

            case "content_block_delta":
                delta = event["delta"]

                match delta["type"]:
                    case "signature_delta":
                        return {
                            "contentBlockDelta": {
                                "contentBlockIndex": event["index"],
                                "delta": {
                                    "reasoningContent": {
                                        "signature": delta["signature"],
                                    },
                                },
                            },
                        }

                    case "thinking_delta":
                        return {
                            "contentBlockDelta": {
                                "contentBlockIndex": event["index"],
                                "delta": {
                                    "reasoningContent": {
                                        "text": delta["thinking"],
                                    },
                                },
                            },
                        }

                    case "input_json_delta":
                        return {
                            "contentBlockDelta": {
                                "contentBlockIndex": event["index"],
                                "delta": {
                                    "toolUse": {
                                        "input": delta["partial_json"],
                                    },
                                },
                            },
                        }

                    case "text_delta":
                        return {
                            "contentBlockDelta": {
                                "contentBlockIndex": event["index"],
                                "delta": {
                                    "text": delta["text"],
                                },
                            },
                        }

                    case _:
                        raise RuntimeError(
                            f"event_type=<content_block_delta>, delta_type=<{delta['type']}> | unknown type"
                        )

            case "content_block_stop":
                return {"contentBlockStop": {"contentBlockIndex": event["index"]}}

            case "message_stop":
                message = event["message"]

                return {"messageStop": {"stopReason": message["stop_reason"]}}

            case "metadata":
                usage = event["usage"]

                return {
                    "metadata": {
                        "usage": {
                            "inputTokens": usage["input_tokens"],
                            "outputTokens": usage["output_tokens"],
                            "totalTokens": usage["input_tokens"] + usage["output_tokens"],
                        },
                        "metrics": {
                            "latencyMs": 0,  # TODO
                        },
                    }
                }

            case _:
                raise RuntimeError(f"event_type=<{event['type']} | unknown type")

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the Anthropic model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.

        Raises:
            ContextWindowOverflowException: If the input exceeds the model's context window.
            ModelThrottledException: If the request is throttled by Anthropic.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("request=<%s>", request)

        logger.debug("invoking model")
        try:
            async with self.client.messages.stream(**request) as stream:
                logger.debug("got response from model")
                async for event in stream:
                    if event.type in AnthropicModel.EVENT_TYPES:
                        yield self.format_chunk(event.model_dump())

                usage = event.message.usage  # type: ignore
                yield self.format_chunk({"type": "metadata", "usage": usage.model_dump()})

        except anthropic.RateLimitError as error:
            raise ModelThrottledException(str(error)) from error

        except anthropic.BadRequestError as error:
            if any(overflow_message in str(error).lower() for overflow_message in AnthropicModel.OVERFLOW_MESSAGES):
                raise ContextWindowOverflowException(str(error)) from error

            raise error

        logger.debug("finished streaming response from model")

    @override
    async def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events with the last being the structured output.
        """
        tool_spec = convert_pydantic_to_tool_spec(output_model)

        response = self.stream(messages=prompt, tool_specs=[tool_spec], system_prompt=system_prompt, **kwargs)
        async for event in process_stream(response):
            yield event

        stop_reason, messages, _, _ = event["stop"]

        if stop_reason != "tool_use":
            raise ValueError(f'Model returned stop_reason: {stop_reason} instead of "tool_use".')

        content = messages["content"]
        output_response: dict[str, Any] | None = None
        for block in content:
            # if the tool use name doesn't match the tool spec name, skip, and if the block is not a tool use, skip.
            # if the tool use name never matches, raise an error.
            if block.get("toolUse") and block["toolUse"]["name"] == tool_spec["name"]:
                output_response = block["toolUse"]["input"]
            else:
                continue

        if output_response is None:
            raise ValueError("No valid tool use or tool use input was found in the Anthropic response.")

        yield {"output": output_model(**output_response)}



================================================
FILE: src/strands/models/bedrock.py
================================================
"""AWS Bedrock model provider.

- Docs: https://aws.amazon.com/bedrock/
"""

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator, Callable, Iterable, Literal, Optional, Type, TypeVar, Union

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import ClientError
from pydantic import BaseModel
from typing_extensions import TypedDict, Unpack, override

from ..event_loop import streaming
from ..tools import convert_pydantic_to_tool_spec
from ..types.content import ContentBlock, Message, Messages
from ..types.exceptions import ContextWindowOverflowException, ModelThrottledException
from ..types.streaming import StreamEvent
from ..types.tools import ToolResult, ToolSpec
from .model import Model

logger = logging.getLogger(__name__)

DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"
DEFAULT_BEDROCK_REGION = "us-west-2"

BEDROCK_CONTEXT_WINDOW_OVERFLOW_MESSAGES = [
    "Input is too long for requested model",
    "input length and `max_tokens` exceed context limit",
    "too many total text bytes",
]

T = TypeVar("T", bound=BaseModel)


class BedrockModel(Model):
    """AWS Bedrock model provider implementation.

    The implementation handles Bedrock-specific features such as:

    - Tool configuration for function calling
    - Guardrails integration
    - Caching points for system prompts and tools
    - Streaming responses
    - Context window overflow detection
    """

    class BedrockConfig(TypedDict, total=False):
        """Configuration options for Bedrock models.

        Attributes:
            additional_args: Any additional arguments to include in the request
            additional_request_fields: Additional fields to include in the Bedrock request
            additional_response_field_paths: Additional response field paths to extract
            cache_prompt: Cache point type for the system prompt
            cache_tools: Cache point type for tools
            guardrail_id: ID of the guardrail to apply
            guardrail_trace: Guardrail trace mode. Defaults to enabled.
            guardrail_version: Version of the guardrail to apply
            guardrail_stream_processing_mode: The guardrail processing mode
            guardrail_redact_input: Flag to redact input if a guardrail is triggered. Defaults to True.
            guardrail_redact_input_message: If a Bedrock Input guardrail triggers, replace the input with this message.
            guardrail_redact_output: Flag to redact output if guardrail is triggered. Defaults to False.
            guardrail_redact_output_message: If a Bedrock Output guardrail triggers, replace output with this message.
            max_tokens: Maximum number of tokens to generate in the response
            model_id: The Bedrock model ID (e.g., "us.anthropic.claude-sonnet-4-20250514-v1:0")
            stop_sequences: List of sequences that will stop generation when encountered
            streaming: Flag to enable/disable streaming. Defaults to True.
            temperature: Controls randomness in generation (higher = more random)
            top_p: Controls diversity via nucleus sampling (alternative to temperature)
        """

        additional_args: Optional[dict[str, Any]]
        additional_request_fields: Optional[dict[str, Any]]
        additional_response_field_paths: Optional[list[str]]
        cache_prompt: Optional[str]
        cache_tools: Optional[str]
        guardrail_id: Optional[str]
        guardrail_trace: Optional[Literal["enabled", "disabled", "enabled_full"]]
        guardrail_stream_processing_mode: Optional[Literal["sync", "async"]]
        guardrail_version: Optional[str]
        guardrail_redact_input: Optional[bool]
        guardrail_redact_input_message: Optional[str]
        guardrail_redact_output: Optional[bool]
        guardrail_redact_output_message: Optional[str]
        max_tokens: Optional[int]
        model_id: str
        stop_sequences: Optional[list[str]]
        streaming: Optional[bool]
        temperature: Optional[float]
        top_p: Optional[float]

    def __init__(
        self,
        *,
        boto_session: Optional[boto3.Session] = None,
        boto_client_config: Optional[BotocoreConfig] = None,
        region_name: Optional[str] = None,
        **model_config: Unpack[BedrockConfig],
    ):
        """Initialize provider instance.

        Args:
            boto_session: Boto Session to use when calling the Bedrock Model.
            boto_client_config: Configuration to use when creating the Bedrock-Runtime Boto Client.
            region_name: AWS region to use for the Bedrock service.
                Defaults to the AWS_REGION environment variable if set, or "us-west-2" if not set.
            **model_config: Configuration options for the Bedrock model.
        """
        if region_name and boto_session:
            raise ValueError("Cannot specify both `region_name` and `boto_session`.")

        self.config = BedrockModel.BedrockConfig(model_id=DEFAULT_BEDROCK_MODEL_ID)
        self.update_config(**model_config)

        logger.debug("config=<%s> | initializing", self.config)

        session = boto_session or boto3.Session()

        # Add strands-agents to the request user agent
        if boto_client_config:
            existing_user_agent = getattr(boto_client_config, "user_agent_extra", None)

            # Append 'strands-agents' to existing user_agent_extra or set it if not present
            if existing_user_agent:
                new_user_agent = f"{existing_user_agent} strands-agents"
            else:
                new_user_agent = "strands-agents"

            client_config = boto_client_config.merge(BotocoreConfig(user_agent_extra=new_user_agent))
        else:
            client_config = BotocoreConfig(user_agent_extra="strands-agents")

        resolved_region = region_name or session.region_name or os.environ.get("AWS_REGION") or DEFAULT_BEDROCK_REGION

        self.client = session.client(
            service_name="bedrock-runtime",
            config=client_config,
            region_name=resolved_region,
        )

        logger.debug("region=<%s> | bedrock client created", self.client.meta.region_name)

    @override
    def update_config(self, **model_config: Unpack[BedrockConfig]) -> None:  # type: ignore
        """Update the Bedrock Model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> BedrockConfig:
        """Get the current Bedrock Model configuration.

        Returns:
            The Bedrock model configuration.
        """
        return self.config

    def format_request(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """Format a Bedrock converse stream request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            A Bedrock converse stream request.
        """
        return {
            "modelId": self.config["model_id"],
            "messages": self._format_bedrock_messages(messages),
            "system": [
                *([{"text": system_prompt}] if system_prompt else []),
                *([{"cachePoint": {"type": self.config["cache_prompt"]}}] if self.config.get("cache_prompt") else []),
            ],
            **(
                {
                    "toolConfig": {
                        "tools": [
                            *[{"toolSpec": tool_spec} for tool_spec in tool_specs],
                            *(
                                [{"cachePoint": {"type": self.config["cache_tools"]}}]
                                if self.config.get("cache_tools")
                                else []
                            ),
                        ],
                        "toolChoice": {"auto": {}},
                    }
                }
                if tool_specs
                else {}
            ),
            **(
                {"additionalModelRequestFields": self.config["additional_request_fields"]}
                if self.config.get("additional_request_fields")
                else {}
            ),
            **(
                {"additionalModelResponseFieldPaths": self.config["additional_response_field_paths"]}
                if self.config.get("additional_response_field_paths")
                else {}
            ),
            **(
                {
                    "guardrailConfig": {
                        "guardrailIdentifier": self.config["guardrail_id"],
                        "guardrailVersion": self.config["guardrail_version"],
                        "trace": self.config.get("guardrail_trace", "enabled"),
                        **(
                            {"streamProcessingMode": self.config.get("guardrail_stream_processing_mode")}
                            if self.config.get("guardrail_stream_processing_mode")
                            else {}
                        ),
                    }
                }
                if self.config.get("guardrail_id") and self.config.get("guardrail_version")
                else {}
            ),
            "inferenceConfig": {
                key: value
                for key, value in [
                    ("maxTokens", self.config.get("max_tokens")),
                    ("temperature", self.config.get("temperature")),
                    ("topP", self.config.get("top_p")),
                    ("stopSequences", self.config.get("stop_sequences")),
                ]
                if value is not None
            },
            **(
                self.config["additional_args"]
                if "additional_args" in self.config and self.config["additional_args"] is not None
                else {}
            ),
        }

    def _format_bedrock_messages(self, messages: Messages) -> Messages:
        """Format messages for Bedrock API compatibility.

        This function ensures messages conform to Bedrock's expected format by:
        - Cleaning tool result content blocks by removing additional fields that may be
          useful for retaining information in hooks but would cause Bedrock validation
          exceptions when presented with unexpected fields
        - Ensuring all message content blocks are properly formatted for the Bedrock API

        Args:
            messages: List of messages to format

        Returns:
            Messages formatted for Bedrock API compatibility

        Note:
            Bedrock will throw validation exceptions when presented with additional
            unexpected fields in tool result blocks.
            https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolResultBlock.html
        """
        cleaned_messages = []

        for message in messages:
            cleaned_content: list[ContentBlock] = []

            for content_block in message["content"]:
                if "toolResult" in content_block:
                    # Create a new content block with only the cleaned toolResult
                    tool_result: ToolResult = content_block["toolResult"]

                    # Keep only the required fields for Bedrock
                    cleaned_tool_result = ToolResult(
                        content=tool_result["content"], toolUseId=tool_result["toolUseId"], status=tool_result["status"]
                    )

                    cleaned_block: ContentBlock = {"toolResult": cleaned_tool_result}
                    cleaned_content.append(cleaned_block)
                else:
                    # Keep other content blocks as-is
                    cleaned_content.append(content_block)

            # Create new message with cleaned content
            cleaned_message: Message = Message(content=cleaned_content, role=message["role"])
            cleaned_messages.append(cleaned_message)

        return cleaned_messages

    def _has_blocked_guardrail(self, guardrail_data: dict[str, Any]) -> bool:
        """Check if guardrail data contains any blocked policies.

        Args:
            guardrail_data: Guardrail data from trace information.

        Returns:
            True if any blocked guardrail is detected, False otherwise.
        """
        input_assessment = guardrail_data.get("inputAssessment", {})
        output_assessments = guardrail_data.get("outputAssessments", {})

        # Check input assessments
        if any(self._find_detected_and_blocked_policy(assessment) for assessment in input_assessment.values()):
            return True

        # Check output assessments
        if any(self._find_detected_and_blocked_policy(assessment) for assessment in output_assessments.values()):
            return True

        return False

    def _generate_redaction_events(self) -> list[StreamEvent]:
        """Generate redaction events based on configuration.

        Returns:
            List of redaction events to yield.
        """
        events: list[StreamEvent] = []

        if self.config.get("guardrail_redact_input", True):
            logger.debug("Redacting user input due to guardrail.")
            events.append(
                {
                    "redactContent": {
                        "redactUserContentMessage": self.config.get(
                            "guardrail_redact_input_message", "[User input redacted.]"
                        )
                    }
                }
            )

        if self.config.get("guardrail_redact_output", False):
            logger.debug("Redacting assistant output due to guardrail.")
            events.append(
                {
                    "redactContent": {
                        "redactAssistantContentMessage": self.config.get(
                            "guardrail_redact_output_message", "[Assistant output redacted.]"
                        )
                    }
                }
            )

        return events

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the Bedrock model.

        This method calls either the Bedrock converse_stream API or the converse API
        based on the streaming parameter in the configuration.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events.

        Raises:
            ContextWindowOverflowException: If the input exceeds the model's context window.
            ModelThrottledException: If the model service is throttling requests.
        """

        def callback(event: Optional[StreamEvent] = None) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)
            if event is None:
                return

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[Optional[StreamEvent]] = asyncio.Queue()

        thread = asyncio.to_thread(self._stream, callback, messages, tool_specs, system_prompt)
        task = asyncio.create_task(thread)

        while True:
            event = await queue.get()
            if event is None:
                break

            yield event

        await task

    def _stream(
        self,
        callback: Callable[..., None],
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        """Stream conversation with the Bedrock model.

        This method operates in a separate thread to avoid blocking the async event loop with the call to
        Bedrock's converse_stream.

        Args:
            callback: Function to send events to the main thread.
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Raises:
            ContextWindowOverflowException: If the input exceeds the model's context window.
            ModelThrottledException: If the model service is throttling requests.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("request=<%s>", request)

        logger.debug("invoking model")
        streaming = self.config.get("streaming", True)

        try:
            logger.debug("got response from model")
            if streaming:
                response = self.client.converse_stream(**request)
                for chunk in response["stream"]:
                    if (
                        "metadata" in chunk
                        and "trace" in chunk["metadata"]
                        and "guardrail" in chunk["metadata"]["trace"]
                    ):
                        guardrail_data = chunk["metadata"]["trace"]["guardrail"]
                        if self._has_blocked_guardrail(guardrail_data):
                            for event in self._generate_redaction_events():
                                callback(event)

                    callback(chunk)

            else:
                response = self.client.converse(**request)
                for event in self._convert_non_streaming_to_streaming(response):
                    callback(event)

                if (
                    "trace" in response
                    and "guardrail" in response["trace"]
                    and self._has_blocked_guardrail(response["trace"]["guardrail"])
                ):
                    for event in self._generate_redaction_events():
                        callback(event)

        except ClientError as e:
            error_message = str(e)

            if e.response["Error"]["Code"] == "ThrottlingException":
                raise ModelThrottledException(error_message) from e

            if any(overflow_message in error_message for overflow_message in BEDROCK_CONTEXT_WINDOW_OVERFLOW_MESSAGES):
                logger.warning("bedrock threw context window overflow error")
                raise ContextWindowOverflowException(e) from e

            region = self.client.meta.region_name

            # add_note added in Python 3.11
            if hasattr(e, "add_note"):
                # Aid in debugging by adding more information
                e.add_note(f"└ Bedrock region: {region}")
                e.add_note(f"└ Model id: {self.config.get('model_id')}")

                if (
                    e.response["Error"]["Code"] == "AccessDeniedException"
                    and "You don't have access to the model" in error_message
                ):
                    e.add_note(
                        "└ For more information see "
                        "https://strandsagents.com/latest/user-guide/concepts/model-providers/amazon-bedrock/#model-access-issue"
                    )

                if (
                    e.response["Error"]["Code"] == "ValidationException"
                    and "with on-demand throughput isn’t supported" in error_message
                ):
                    e.add_note(
                        "└ For more information see "
                        "https://strandsagents.com/latest/user-guide/concepts/model-providers/amazon-bedrock/#on-demand-throughput-isnt-supported"
                    )

            raise e

        finally:
            callback()
            logger.debug("finished streaming response from model")

    def _convert_non_streaming_to_streaming(self, response: dict[str, Any]) -> Iterable[StreamEvent]:
        """Convert a non-streaming response to the streaming format.

        Args:
            response: The non-streaming response from the Bedrock model.

        Returns:
            An iterable of response events in the streaming format.
        """
        # Yield messageStart event
        yield {"messageStart": {"role": response["output"]["message"]["role"]}}

        # Process content blocks
        for content in response["output"]["message"]["content"]:
            # Yield contentBlockStart event if needed
            if "toolUse" in content:
                yield {
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "toolUseId": content["toolUse"]["toolUseId"],
                                "name": content["toolUse"]["name"],
                            }
                        },
                    }
                }

                # For tool use, we need to yield the input as a delta
                input_value = json.dumps(content["toolUse"]["input"])

                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": input_value}}}}
            elif "text" in content:
                # Then yield the text as a delta
                yield {
                    "contentBlockDelta": {
                        "delta": {"text": content["text"]},
                    }
                }
            elif "reasoningContent" in content:
                # Then yield the reasoning content as a delta
                yield {
                    "contentBlockDelta": {
                        "delta": {"reasoningContent": {"text": content["reasoningContent"]["reasoningText"]["text"]}}
                    }
                }

                if "signature" in content["reasoningContent"]["reasoningText"]:
                    yield {
                        "contentBlockDelta": {
                            "delta": {
                                "reasoningContent": {
                                    "signature": content["reasoningContent"]["reasoningText"]["signature"]
                                }
                            }
                        }
                    }

            # Yield contentBlockStop event
            yield {"contentBlockStop": {}}

        # Yield messageStop event
        yield {
            "messageStop": {
                "stopReason": response["stopReason"],
                "additionalModelResponseFields": response.get("additionalModelResponseFields"),
            }
        }

        # Yield metadata event
        if "usage" in response or "metrics" in response or "trace" in response:
            metadata: StreamEvent = {"metadata": {}}
            if "usage" in response:
                metadata["metadata"]["usage"] = response["usage"]
            if "metrics" in response:
                metadata["metadata"]["metrics"] = response["metrics"]
            if "trace" in response:
                metadata["metadata"]["trace"] = response["trace"]
            yield metadata

    def _find_detected_and_blocked_policy(self, input: Any) -> bool:
        """Recursively checks if the assessment contains a detected and blocked guardrail.

        Args:
            input: The assessment to check.

        Returns:
            True if the input contains a detected and blocked guardrail, False otherwise.

        """
        # Check if input is a dictionary
        if isinstance(input, dict):
            # Check if current dictionary has action: BLOCKED and detected: true
            if input.get("action") == "BLOCKED" and input.get("detected") and isinstance(input.get("detected"), bool):
                return True

            # Recursively check all values in the dictionary
            for value in input.values():
                if isinstance(value, dict):
                    return self._find_detected_and_blocked_policy(value)
                # Handle case where value is a list of dictionaries
                elif isinstance(value, list):
                    for item in value:
                        return self._find_detected_and_blocked_policy(item)
        elif isinstance(input, list):
            # Handle case where input is a list of dictionaries
            for item in input:
                return self._find_detected_and_blocked_policy(item)
        # Otherwise return False
        return False

    @override
    async def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events with the last being the structured output.
        """
        tool_spec = convert_pydantic_to_tool_spec(output_model)

        response = self.stream(messages=prompt, tool_specs=[tool_spec], system_prompt=system_prompt, **kwargs)
        async for event in streaming.process_stream(response):
            yield event

        stop_reason, messages, _, _ = event["stop"]

        if stop_reason != "tool_use":
            raise ValueError(f'Model returned stop_reason: {stop_reason} instead of "tool_use".')

        content = messages["content"]
        output_response: dict[str, Any] | None = None
        for block in content:
            # if the tool use name doesn't match the tool spec name, skip, and if the block is not a tool use, skip.
            # if the tool use name never matches, raise an error.
            if block.get("toolUse") and block["toolUse"]["name"] == tool_spec["name"]:
                output_response = block["toolUse"]["input"]
            else:
                continue

        if output_response is None:
            raise ValueError("No valid tool use or tool use input was found in the Bedrock response.")

        yield {"output": output_model(**output_response)}



================================================
FILE: src/strands/models/litellm.py
================================================
"""LiteLLM model provider.

- Docs: https://docs.litellm.ai/
"""

import json
import logging
from typing import Any, AsyncGenerator, Optional, Type, TypedDict, TypeVar, Union, cast

import litellm
from litellm.utils import supports_response_schema
from pydantic import BaseModel
from typing_extensions import Unpack, override

from ..types.content import ContentBlock, Messages
from ..types.streaming import StreamEvent
from ..types.tools import ToolSpec
from .openai import OpenAIModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LiteLLMModel(OpenAIModel):
    """LiteLLM model provider implementation."""

    class LiteLLMConfig(TypedDict, total=False):
        """Configuration options for LiteLLM models.

        Attributes:
            model_id: Model ID (e.g., "openai/gpt-4o", "anthropic/claude-3-sonnet").
                For a complete list of supported models, see https://docs.litellm.ai/docs/providers.
            params: Model parameters (e.g., max_tokens).
                For a complete list of supported parameters, see
                https://docs.litellm.ai/docs/completion/input#input-params-1.
        """

        model_id: str
        params: Optional[dict[str, Any]]

    def __init__(self, client_args: Optional[dict[str, Any]] = None, **model_config: Unpack[LiteLLMConfig]) -> None:
        """Initialize provider instance.

        Args:
            client_args: Arguments for the LiteLLM client.
                For a complete list of supported arguments, see
                https://github.com/BerriAI/litellm/blob/main/litellm/main.py.
            **model_config: Configuration options for the LiteLLM model.
        """
        self.client_args = client_args or {}
        self.config = dict(model_config)

        logger.debug("config=<%s> | initializing", self.config)

    @override
    def update_config(self, **model_config: Unpack[LiteLLMConfig]) -> None:  # type: ignore[override]
        """Update the LiteLLM model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> LiteLLMConfig:
        """Get the LiteLLM model configuration.

        Returns:
            The LiteLLM model configuration.
        """
        return cast(LiteLLMModel.LiteLLMConfig, self.config)

    @override
    @classmethod
    def format_request_message_content(cls, content: ContentBlock) -> dict[str, Any]:
        """Format a LiteLLM content block.

        Args:
            content: Message content.

        Returns:
            LiteLLM formatted content block.

        Raises:
            TypeError: If the content block type cannot be converted to a LiteLLM-compatible format.
        """
        if "reasoningContent" in content:
            return {
                "signature": content["reasoningContent"]["reasoningText"]["signature"],
                "thinking": content["reasoningContent"]["reasoningText"]["text"],
                "type": "thinking",
            }

        if "video" in content:
            return {
                "type": "video_url",
                "video_url": {
                    "detail": "auto",
                    "url": content["video"]["source"]["bytes"],
                },
            }

        return super().format_request_message_content(content)

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the LiteLLM model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("request=<%s>", request)

        logger.debug("invoking model")
        response = await litellm.acompletion(**self.client_args, **request)

        logger.debug("got response from model")
        yield self.format_chunk({"chunk_type": "message_start"})
        yield self.format_chunk({"chunk_type": "content_start", "data_type": "text"})

        tool_calls: dict[int, list[Any]] = {}

        async for event in response:
            # Defensive: skip events with empty or missing choices
            if not getattr(event, "choices", None):
                continue
            choice = event.choices[0]

            if choice.delta.content:
                yield self.format_chunk(
                    {"chunk_type": "content_delta", "data_type": "text", "data": choice.delta.content}
                )

            if hasattr(choice.delta, "reasoning_content") and choice.delta.reasoning_content:
                yield self.format_chunk(
                    {
                        "chunk_type": "content_delta",
                        "data_type": "reasoning_content",
                        "data": choice.delta.reasoning_content,
                    }
                )

            for tool_call in choice.delta.tool_calls or []:
                tool_calls.setdefault(tool_call.index, []).append(tool_call)

            if choice.finish_reason:
                break

        yield self.format_chunk({"chunk_type": "content_stop", "data_type": "text"})

        for tool_deltas in tool_calls.values():
            yield self.format_chunk({"chunk_type": "content_start", "data_type": "tool", "data": tool_deltas[0]})

            for tool_delta in tool_deltas:
                yield self.format_chunk({"chunk_type": "content_delta", "data_type": "tool", "data": tool_delta})

            yield self.format_chunk({"chunk_type": "content_stop", "data_type": "tool"})

        yield self.format_chunk({"chunk_type": "message_stop", "data": choice.finish_reason})

        # Skip remaining events as we don't have use for anything except the final usage payload
        async for event in response:
            _ = event

        if event.usage:
            yield self.format_chunk({"chunk_type": "metadata", "data": event.usage})

        logger.debug("finished streaming response from model")

    @override
    async def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events with the last being the structured output.
        """
        response = await litellm.acompletion(
            **self.client_args,
            model=self.get_config()["model_id"],
            messages=self.format_request(prompt, system_prompt=system_prompt)["messages"],
            response_format=output_model,
        )

        if not supports_response_schema(self.get_config()["model_id"]):
            raise ValueError("Model does not support response_format")
        if len(response.choices) > 1:
            raise ValueError("Multiple choices found in the response.")

        # Find the first choice with tool_calls
        for choice in response.choices:
            if choice.finish_reason == "tool_calls":
                try:
                    # Parse the tool call content as JSON
                    tool_call_data = json.loads(choice.message.content)
                    # Instantiate the output model with the parsed data
                    yield {"output": output_model(**tool_call_data)}
                    return
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    raise ValueError(f"Failed to parse or load content into model: {e}") from e

        # If no tool_calls found, raise an error
        raise ValueError("No tool_calls found in response")



================================================
FILE: src/strands/models/llamaapi.py
================================================
# Copyright (c) Meta Platforms, Inc. and affiliates
"""Llama API model provider.

- Docs: https://llama.developer.meta.com/
"""

import base64
import json
import logging
import mimetypes
from typing import Any, AsyncGenerator, Optional, Type, TypeVar, Union, cast

import llama_api_client
from llama_api_client import LlamaAPIClient
from pydantic import BaseModel
from typing_extensions import TypedDict, Unpack, override

from ..types.content import ContentBlock, Messages
from ..types.exceptions import ModelThrottledException
from ..types.streaming import StreamEvent, Usage
from ..types.tools import ToolResult, ToolSpec, ToolUse
from .model import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LlamaAPIModel(Model):
    """Llama API model provider implementation."""

    class LlamaConfig(TypedDict, total=False):
        """Configuration options for Llama API models.

        Attributes:
            model_id: Model ID (e.g., "Llama-4-Maverick-17B-128E-Instruct-FP8").
            repetition_penalty: Repetition penalty.
            temperature: Temperature.
            top_p: Top-p.
            max_completion_tokens: Maximum completion tokens.
            top_k: Top-k.
        """

        model_id: str
        repetition_penalty: Optional[float]
        temperature: Optional[float]
        top_p: Optional[float]
        max_completion_tokens: Optional[int]
        top_k: Optional[int]

    def __init__(
        self,
        *,
        client_args: Optional[dict[str, Any]] = None,
        **model_config: Unpack[LlamaConfig],
    ) -> None:
        """Initialize provider instance.

        Args:
            client_args: Arguments for the Llama API client.
            **model_config: Configuration options for the Llama API model.
        """
        self.config = LlamaAPIModel.LlamaConfig(**model_config)
        logger.debug("config=<%s> | initializing", self.config)

        if not client_args:
            self.client = LlamaAPIClient()
        else:
            self.client = LlamaAPIClient(**client_args)

    @override
    def update_config(self, **model_config: Unpack[LlamaConfig]) -> None:  # type: ignore
        """Update the Llama API Model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> LlamaConfig:
        """Get the Llama API model configuration.

        Returns:
            The Llama API model configuration.
        """
        return self.config

    def _format_request_message_content(self, content: ContentBlock) -> dict[str, Any]:
        """Format a LlamaAPI content block.

        - NOTE: "reasoningContent" and "video" are not supported currently.

        Args:
            content: Message content.

        Returns:
            LllamaAPI formatted content block.

        Raises:
            TypeError: If the content block type cannot be converted to a LlamaAPI-compatible format.
        """
        if "image" in content:
            mime_type = mimetypes.types_map.get(f".{content['image']['format']}", "application/octet-stream")
            image_data = base64.b64encode(content["image"]["source"]["bytes"]).decode("utf-8")

            return {
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_data}",
                },
                "type": "image_url",
            }

        if "text" in content:
            return {"text": content["text"], "type": "text"}

        raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

    def _format_request_message_tool_call(self, tool_use: ToolUse) -> dict[str, Any]:
        """Format a Llama API tool call.

        Args:
            tool_use: Tool use requested by the model.

        Returns:
            Llama API formatted tool call.
        """
        return {
            "function": {
                "arguments": json.dumps(tool_use["input"]),
                "name": tool_use["name"],
            },
            "id": tool_use["toolUseId"],
        }

    def _format_request_tool_message(self, tool_result: ToolResult) -> dict[str, Any]:
        """Format a Llama API tool message.

        Args:
            tool_result: Tool result collected from a tool execution.

        Returns:
            Llama API formatted tool message.
        """
        contents = cast(
            list[ContentBlock],
            [
                {"text": json.dumps(content["json"])} if "json" in content else content
                for content in tool_result["content"]
            ],
        )

        return {
            "role": "tool",
            "tool_call_id": tool_result["toolUseId"],
            "content": [self._format_request_message_content(content) for content in contents],
        }

    def _format_request_messages(self, messages: Messages, system_prompt: Optional[str] = None) -> list[dict[str, Any]]:
        """Format a LlamaAPI compatible messages array.

        Args:
            messages: List of message objects to be processed by the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An LlamaAPI compatible messages array.
        """
        formatted_messages: list[dict[str, Any]]
        formatted_messages = [{"role": "system", "content": system_prompt}] if system_prompt else []

        for message in messages:
            contents = message["content"]

            formatted_contents: list[dict[str, Any]] | dict[str, Any] | str = ""
            formatted_contents = [
                self._format_request_message_content(content)
                for content in contents
                if not any(block_type in content for block_type in ["toolResult", "toolUse"])
            ]
            formatted_tool_calls = [
                self._format_request_message_tool_call(content["toolUse"])
                for content in contents
                if "toolUse" in content
            ]
            formatted_tool_messages = [
                self._format_request_tool_message(content["toolResult"])
                for content in contents
                if "toolResult" in content
            ]

            if message["role"] == "assistant":
                formatted_contents = formatted_contents[0] if formatted_contents else ""

            formatted_message = {
                "role": message["role"],
                "content": formatted_contents if len(formatted_contents) > 0 else "",
                **({"tool_calls": formatted_tool_calls} if formatted_tool_calls else {}),
            }
            formatted_messages.append(formatted_message)
            formatted_messages.extend(formatted_tool_messages)

        return [message for message in formatted_messages if message["content"] or "tool_calls" in message]

    def format_request(
        self, messages: Messages, tool_specs: Optional[list[ToolSpec]] = None, system_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        """Format a Llama API chat streaming request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An Llama API chat streaming request.

        Raises:
            TypeError: If a message contains a content block type that cannot be converted to a LlamaAPI-compatible
                format.
        """
        request = {
            "messages": self._format_request_messages(messages, system_prompt),
            "model": self.config["model_id"],
            "stream": True,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool_spec["name"],
                        "description": tool_spec["description"],
                        "parameters": tool_spec["inputSchema"]["json"],
                    },
                }
                for tool_spec in tool_specs or []
            ],
        }
        if "temperature" in self.config:
            request["temperature"] = self.config["temperature"]
        if "top_p" in self.config:
            request["top_p"] = self.config["top_p"]
        if "repetition_penalty" in self.config:
            request["repetition_penalty"] = self.config["repetition_penalty"]
        if "max_completion_tokens" in self.config:
            request["max_completion_tokens"] = self.config["max_completion_tokens"]
        if "top_k" in self.config:
            request["top_k"] = self.config["top_k"]

        return request

    def format_chunk(self, event: dict[str, Any]) -> StreamEvent:
        """Format the Llama API model response events into standardized message chunks.

        Args:
            event: A response event from the model.

        Returns:
            The formatted chunk.
        """
        match event["chunk_type"]:
            case "message_start":
                return {"messageStart": {"role": "assistant"}}

            case "content_start":
                if event["data_type"] == "text":
                    return {"contentBlockStart": {"start": {}}}

                return {
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "name": event["data"].function.name,
                                "toolUseId": event["data"].id,
                            }
                        }
                    }
                }

            case "content_delta":
                if event["data_type"] == "text":
                    return {"contentBlockDelta": {"delta": {"text": event["data"]}}}

                return {"contentBlockDelta": {"delta": {"toolUse": {"input": event["data"].function.arguments}}}}

            case "content_stop":
                return {"contentBlockStop": {}}

            case "message_stop":
                match event["data"]:
                    case "tool_calls":
                        return {"messageStop": {"stopReason": "tool_use"}}
                    case "length":
                        return {"messageStop": {"stopReason": "max_tokens"}}
                    case _:
                        return {"messageStop": {"stopReason": "end_turn"}}

            case "metadata":
                usage = {}
                for metrics in event["data"]:
                    if metrics.metric == "num_prompt_tokens":
                        usage["inputTokens"] = metrics.value
                    elif metrics.metric == "num_completion_tokens":
                        usage["outputTokens"] = metrics.value
                    elif metrics.metric == "num_total_tokens":
                        usage["totalTokens"] = metrics.value

                usage_type = Usage(
                    inputTokens=usage["inputTokens"],
                    outputTokens=usage["outputTokens"],
                    totalTokens=usage["totalTokens"],
                )
                return {
                    "metadata": {
                        "usage": usage_type,
                        "metrics": {
                            "latencyMs": 0,  # TODO
                        },
                    },
                }

            case _:
                raise RuntimeError(f"chunk_type=<{event['chunk_type']} | unknown type")

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the LlamaAPI model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.

        Raises:
            ModelThrottledException: When the model service is throttling requests from the client.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("request=<%s>", request)

        logger.debug("invoking model")
        try:
            response = self.client.chat.completions.create(**request)
        except llama_api_client.RateLimitError as e:
            raise ModelThrottledException(str(e)) from e

        logger.debug("got response from model")
        yield self.format_chunk({"chunk_type": "message_start"})

        stop_reason = None
        tool_calls: dict[Any, list[Any]] = {}
        curr_tool_call_id = None

        metrics_event = None
        for chunk in response:
            if chunk.event.event_type == "start":
                yield self.format_chunk({"chunk_type": "content_start", "data_type": "text"})
            elif chunk.event.event_type in ["progress", "complete"] and chunk.event.delta.type == "text":
                yield self.format_chunk(
                    {"chunk_type": "content_delta", "data_type": "text", "data": chunk.event.delta.text}
                )
            else:
                if chunk.event.delta.type == "tool_call":
                    if chunk.event.delta.id:
                        curr_tool_call_id = chunk.event.delta.id

                    if curr_tool_call_id not in tool_calls:
                        tool_calls[curr_tool_call_id] = []
                    tool_calls[curr_tool_call_id].append(chunk.event.delta)
                elif chunk.event.event_type == "metrics":
                    metrics_event = chunk.event.metrics
                else:
                    yield self.format_chunk(chunk)

            if stop_reason is None:
                stop_reason = chunk.event.stop_reason

            # stopped generation
            if stop_reason:
                yield self.format_chunk({"chunk_type": "content_stop", "data_type": "text"})

        for tool_deltas in tool_calls.values():
            tool_start, tool_deltas = tool_deltas[0], tool_deltas[1:]
            yield self.format_chunk({"chunk_type": "content_start", "data_type": "tool", "data": tool_start})

            for tool_delta in tool_deltas:
                yield self.format_chunk({"chunk_type": "content_delta", "data_type": "tool", "data": tool_delta})

            yield self.format_chunk({"chunk_type": "content_stop", "data_type": "tool"})

        yield self.format_chunk({"chunk_type": "message_stop", "data": stop_reason})

        # we may have a metrics event here
        if metrics_event:
            yield self.format_chunk({"chunk_type": "metadata", "data": metrics_event})

        logger.debug("finished streaming response from model")

    @override
    def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events with the last being the structured output.

        Raises:
            NotImplementedError: Structured output is not currently supported for LlamaAPI models.
        """
        # response_format: ResponseFormat = {
        #     "type": "json_schema",
        #     "json_schema": {
        #         "name": output_model.__name__,
        #         "schema": output_model.model_json_schema(),
        #     },
        # }
        # response = self.client.chat.completions.create(
        #     model=self.config["model_id"],
        #     messages=self.format_request(prompt)["messages"],
        #     response_format=response_format,
        # )
        raise NotImplementedError("Strands sdk-python does not implement this in the Llama API Preview.")



================================================
FILE: src/strands/models/mistral.py
================================================
"""Mistral AI model provider.

- Docs: https://docs.mistral.ai/
"""

import base64
import json
import logging
from typing import Any, AsyncGenerator, Iterable, Optional, Type, TypeVar, Union

import mistralai
from pydantic import BaseModel
from typing_extensions import TypedDict, Unpack, override

from ..types.content import ContentBlock, Messages
from ..types.exceptions import ModelThrottledException
from ..types.streaming import StopReason, StreamEvent
from ..types.tools import ToolResult, ToolSpec, ToolUse
from .model import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class MistralModel(Model):
    """Mistral API model provider implementation.

    The implementation handles Mistral-specific features such as:

    - Chat and text completions
    - Streaming responses
    - Tool/function calling
    - System prompts
    """

    class MistralConfig(TypedDict, total=False):
        """Configuration parameters for Mistral models.

        Attributes:
            model_id: Mistral model ID (e.g., "mistral-large-latest", "mistral-medium-latest").
            max_tokens: Maximum number of tokens to generate in the response.
            temperature: Controls randomness in generation (0.0 to 1.0).
            top_p: Controls diversity via nucleus sampling.
            stream: Whether to enable streaming responses.
        """

        model_id: str
        max_tokens: Optional[int]
        temperature: Optional[float]
        top_p: Optional[float]
        stream: Optional[bool]

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        client_args: Optional[dict[str, Any]] = None,
        **model_config: Unpack[MistralConfig],
    ) -> None:
        """Initialize provider instance.

        Args:
            api_key: Mistral API key. If not provided, will use MISTRAL_API_KEY env var.
            client_args: Additional arguments for the Mistral client.
            **model_config: Configuration options for the Mistral model.
        """
        if "temperature" in model_config and model_config["temperature"] is not None:
            temp = model_config["temperature"]
            if not 0.0 <= temp <= 1.0:
                raise ValueError(f"temperature must be between 0.0 and 1.0, got {temp}")
            # Warn if temperature is above recommended range
            if temp > 0.7:
                logger.warning(
                    "temperature=%s is above the recommended range (0.0-0.7). "
                    "High values may produce unpredictable results.",
                    temp,
                )

        if "top_p" in model_config and model_config["top_p"] is not None:
            top_p = model_config["top_p"]
            if not 0.0 <= top_p <= 1.0:
                raise ValueError(f"top_p must be between 0.0 and 1.0, got {top_p}")

        self.config = MistralModel.MistralConfig(**model_config)

        # Set default stream to True if not specified
        if "stream" not in self.config:
            self.config["stream"] = True

        logger.debug("config=<%s> | initializing", self.config)

        self.client_args = client_args or {}
        if api_key:
            self.client_args["api_key"] = api_key

    @override
    def update_config(self, **model_config: Unpack[MistralConfig]) -> None:  # type: ignore
        """Update the Mistral Model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> MistralConfig:
        """Get the Mistral model configuration.

        Returns:
            The Mistral model configuration.
        """
        return self.config

    def _format_request_message_content(self, content: ContentBlock) -> Union[str, dict[str, Any]]:
        """Format a Mistral content block.

        Args:
            content: Message content.

        Returns:
            Mistral formatted content.

        Raises:
            TypeError: If the content block type cannot be converted to a Mistral-compatible format.
        """
        if "text" in content:
            return content["text"]

        if "image" in content:
            image_data = content["image"]

            if "source" in image_data:
                image_bytes = image_data["source"]["bytes"]
                base64_data = base64.b64encode(image_bytes).decode("utf-8")
                format_value = image_data.get("format", "jpeg")
                media_type = f"image/{format_value}"
                return {"type": "image_url", "image_url": f"data:{media_type};base64,{base64_data}"}

            raise TypeError("content_type=<image> | unsupported image format")

        raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

    def _format_request_message_tool_call(self, tool_use: ToolUse) -> dict[str, Any]:
        """Format a Mistral tool call.

        Args:
            tool_use: Tool use requested by the model.

        Returns:
            Mistral formatted tool call.
        """
        return {
            "function": {
                "name": tool_use["name"],
                "arguments": json.dumps(tool_use["input"]),
            },
            "id": tool_use["toolUseId"],
            "type": "function",
        }

    def _format_request_tool_message(self, tool_result: ToolResult) -> dict[str, Any]:
        """Format a Mistral tool message.

        Args:
            tool_result: Tool result collected from a tool execution.

        Returns:
            Mistral formatted tool message.
        """
        content_parts: list[str] = []
        for content in tool_result["content"]:
            if "json" in content:
                content_parts.append(json.dumps(content["json"]))
            elif "text" in content:
                content_parts.append(content["text"])

        return {
            "role": "tool",
            "name": tool_result["toolUseId"].split("_")[0]
            if "_" in tool_result["toolUseId"]
            else tool_result["toolUseId"],
            "content": "\n".join(content_parts),
            "tool_call_id": tool_result["toolUseId"],
        }

    def _format_request_messages(self, messages: Messages, system_prompt: Optional[str] = None) -> list[dict[str, Any]]:
        """Format a Mistral compatible messages array.

        Args:
            messages: List of message objects to be processed by the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            A Mistral compatible messages array.
        """
        formatted_messages: list[dict[str, Any]] = []

        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for message in messages:
            role = message["role"]
            contents = message["content"]

            text_contents: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            tool_messages: list[dict[str, Any]] = []

            for content in contents:
                if "text" in content:
                    formatted_content = self._format_request_message_content(content)
                    if isinstance(formatted_content, str):
                        text_contents.append(formatted_content)
                elif "toolUse" in content:
                    tool_calls.append(self._format_request_message_tool_call(content["toolUse"]))
                elif "toolResult" in content:
                    tool_messages.append(self._format_request_tool_message(content["toolResult"]))

            if text_contents or tool_calls:
                formatted_message: dict[str, Any] = {
                    "role": role,
                    "content": " ".join(text_contents) if text_contents else "",
                }

                if tool_calls:
                    formatted_message["tool_calls"] = tool_calls

                formatted_messages.append(formatted_message)

            formatted_messages.extend(tool_messages)

        return formatted_messages

    def format_request(
        self, messages: Messages, tool_specs: Optional[list[ToolSpec]] = None, system_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        """Format a Mistral chat streaming request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            A Mistral chat streaming request.

        Raises:
            TypeError: If a message contains a content block type that cannot be converted to a Mistral-compatible
                format.
        """
        request: dict[str, Any] = {
            "model": self.config["model_id"],
            "messages": self._format_request_messages(messages, system_prompt),
        }

        if "max_tokens" in self.config:
            request["max_tokens"] = self.config["max_tokens"]
        if "temperature" in self.config:
            request["temperature"] = self.config["temperature"]
        if "top_p" in self.config:
            request["top_p"] = self.config["top_p"]
        if "stream" in self.config:
            request["stream"] = self.config["stream"]

        if tool_specs:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool_spec["name"],
                        "description": tool_spec["description"],
                        "parameters": tool_spec["inputSchema"]["json"],
                    },
                }
                for tool_spec in tool_specs
            ]

        return request

    def format_chunk(self, event: dict[str, Any]) -> StreamEvent:
        """Format the Mistral response events into standardized message chunks.

        Args:
            event: A response event from the Mistral model.

        Returns:
            The formatted chunk.

        Raises:
            RuntimeError: If chunk_type is not recognized.
        """
        match event["chunk_type"]:
            case "message_start":
                return {"messageStart": {"role": "assistant"}}

            case "content_start":
                if event["data_type"] == "text":
                    return {"contentBlockStart": {"start": {}}}

                tool_call = event["data"]
                return {
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "name": tool_call.function.name,
                                "toolUseId": tool_call.id,
                            }
                        }
                    }
                }

            case "content_delta":
                if event["data_type"] == "text":
                    return {"contentBlockDelta": {"delta": {"text": event["data"]}}}

                return {"contentBlockDelta": {"delta": {"toolUse": {"input": event["data"]}}}}

            case "content_stop":
                return {"contentBlockStop": {}}

            case "message_stop":
                reason: StopReason
                if event["data"] == "tool_calls":
                    reason = "tool_use"
                elif event["data"] == "length":
                    reason = "max_tokens"
                else:
                    reason = "end_turn"

                return {"messageStop": {"stopReason": reason}}

            case "metadata":
                usage = event["data"]
                return {
                    "metadata": {
                        "usage": {
                            "inputTokens": usage.prompt_tokens,
                            "outputTokens": usage.completion_tokens,
                            "totalTokens": usage.total_tokens,
                        },
                        "metrics": {
                            "latencyMs": event.get("latency_ms", 0),
                        },
                    },
                }

            case _:
                raise RuntimeError(f"chunk_type=<{event['chunk_type']}> | unknown type")

    def _handle_non_streaming_response(self, response: Any) -> Iterable[dict[str, Any]]:
        """Handle non-streaming response from Mistral API.

        Args:
            response: The non-streaming response from Mistral.

        Yields:
            Formatted events that match the streaming format.
        """
        yield {"chunk_type": "message_start"}

        content_started = False

        if response.choices and response.choices[0].message:
            message = response.choices[0].message

            if hasattr(message, "content") and message.content:
                if not content_started:
                    yield {"chunk_type": "content_start", "data_type": "text"}
                    content_started = True

                yield {"chunk_type": "content_delta", "data_type": "text", "data": message.content}

                yield {"chunk_type": "content_stop"}

            if hasattr(message, "tool_calls") and message.tool_calls:
                for tool_call in message.tool_calls:
                    yield {"chunk_type": "content_start", "data_type": "tool", "data": tool_call}

                    if hasattr(tool_call.function, "arguments"):
                        yield {"chunk_type": "content_delta", "data_type": "tool", "data": tool_call.function.arguments}

                    yield {"chunk_type": "content_stop"}

            finish_reason = response.choices[0].finish_reason if response.choices[0].finish_reason else "stop"
            yield {"chunk_type": "message_stop", "data": finish_reason}

        if hasattr(response, "usage") and response.usage:
            yield {"chunk_type": "metadata", "data": response.usage}

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the Mistral model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.

        Raises:
            ModelThrottledException: When the model service is throttling requests.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("request=<%s>", request)

        logger.debug("invoking model")
        try:
            logger.debug("got response from model")
            if not self.config.get("stream", True):
                # Use non-streaming API
                async with mistralai.Mistral(**self.client_args) as client:
                    response = await client.chat.complete_async(**request)
                    for event in self._handle_non_streaming_response(response):
                        yield self.format_chunk(event)

                return

            # Use the streaming API
            async with mistralai.Mistral(**self.client_args) as client:
                stream_response = await client.chat.stream_async(**request)

                yield self.format_chunk({"chunk_type": "message_start"})

                content_started = False
                tool_calls: dict[str, list[Any]] = {}
                accumulated_text = ""

                async for chunk in stream_response:
                    if hasattr(chunk, "data") and hasattr(chunk.data, "choices") and chunk.data.choices:
                        choice = chunk.data.choices[0]

                        if hasattr(choice, "delta"):
                            delta = choice.delta

                            if hasattr(delta, "content") and delta.content:
                                if not content_started:
                                    yield self.format_chunk({"chunk_type": "content_start", "data_type": "text"})
                                    content_started = True

                                yield self.format_chunk(
                                    {"chunk_type": "content_delta", "data_type": "text", "data": delta.content}
                                )
                                accumulated_text += delta.content

                            if hasattr(delta, "tool_calls") and delta.tool_calls:
                                for tool_call in delta.tool_calls:
                                    tool_id = tool_call.id
                                    tool_calls.setdefault(tool_id, []).append(tool_call)

                        if hasattr(choice, "finish_reason") and choice.finish_reason:
                            if content_started:
                                yield self.format_chunk({"chunk_type": "content_stop", "data_type": "text"})

                            for tool_deltas in tool_calls.values():
                                yield self.format_chunk(
                                    {"chunk_type": "content_start", "data_type": "tool", "data": tool_deltas[0]}
                                )

                                for tool_delta in tool_deltas:
                                    if hasattr(tool_delta.function, "arguments"):
                                        yield self.format_chunk(
                                            {
                                                "chunk_type": "content_delta",
                                                "data_type": "tool",
                                                "data": tool_delta.function.arguments,
                                            }
                                        )

                                yield self.format_chunk({"chunk_type": "content_stop", "data_type": "tool"})

                            yield self.format_chunk({"chunk_type": "message_stop", "data": choice.finish_reason})

                            if hasattr(chunk, "usage"):
                                yield self.format_chunk({"chunk_type": "metadata", "data": chunk.usage})

        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                raise ModelThrottledException(str(e)) from e
            raise

        logger.debug("finished streaming response from model")

    @override
    async def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Returns:
            An instance of the output model with the generated data.

        Raises:
            ValueError: If the response cannot be parsed into the output model.
        """
        tool_spec: ToolSpec = {
            "name": f"extract_{output_model.__name__.lower()}",
            "description": f"Extract structured data in the format of {output_model.__name__}",
            "inputSchema": {"json": output_model.model_json_schema()},
        }

        formatted_request = self.format_request(messages=prompt, tool_specs=[tool_spec], system_prompt=system_prompt)

        formatted_request["tool_choice"] = "any"
        formatted_request["parallel_tool_calls"] = False

        async with mistralai.Mistral(**self.client_args) as client:
            response = await client.chat.complete_async(**formatted_request)

        if response.choices and response.choices[0].message.tool_calls:
            tool_call = response.choices[0].message.tool_calls[0]
            try:
                # Handle both string and dict arguments
                if isinstance(tool_call.function.arguments, str):
                    arguments = json.loads(tool_call.function.arguments)
                else:
                    arguments = tool_call.function.arguments
                yield {"output": output_model(**arguments)}
                return
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                raise ValueError(f"Failed to parse tool call arguments into model: {e}") from e

        raise ValueError("No tool calls found in response")



================================================
FILE: src/strands/models/model.py
================================================
"""Abstract base class for Agent model providers."""

import abc
import logging
from typing import Any, AsyncGenerator, AsyncIterable, Optional, Type, TypeVar, Union

from pydantic import BaseModel

from ..types.content import Messages
from ..types.streaming import StreamEvent
from ..types.tools import ToolSpec

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class Model(abc.ABC):
    """Abstract base class for Agent model providers.

    This class defines the interface for all model implementations in the Strands Agents SDK. It provides a
    standardized way to configure and process requests for different AI model providers.
    """

    @abc.abstractmethod
    # pragma: no cover
    def update_config(self, **model_config: Any) -> None:
        """Update the model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        pass

    @abc.abstractmethod
    # pragma: no cover
    def get_config(self) -> Any:
        """Return the model configuration.

        Returns:
            The model's configuration.
        """
        pass

    @abc.abstractmethod
    # pragma: no cover
    def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events with the last being the structured output.

        Raises:
            ValidationException: The response format from the model does not match the output_model
        """
        pass

    @abc.abstractmethod
    # pragma: no cover
    def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        """Stream conversation with the model.

        This method handles the full lifecycle of conversing with the model:

        1. Format the messages, tool specs, and configuration into a streaming request
        2. Send the request to the model
        3. Yield the formatted message chunks

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.

        Raises:
            ModelThrottledException: When the model service is throttling requests from the client.
        """
        pass



================================================
FILE: src/strands/models/ollama.py
================================================
"""Ollama model provider.

- Docs: https://ollama.com/
"""

import json
import logging
from typing import Any, AsyncGenerator, Optional, Type, TypeVar, Union, cast

import ollama
from pydantic import BaseModel
from typing_extensions import TypedDict, Unpack, override

from ..types.content import ContentBlock, Messages
from ..types.streaming import StopReason, StreamEvent
from ..types.tools import ToolSpec
from .model import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OllamaModel(Model):
    """Ollama model provider implementation.

    The implementation handles Ollama-specific features such as:

    - Local model invocation
    - Streaming responses
    - Tool/function calling
    """

    class OllamaConfig(TypedDict, total=False):
        """Configuration parameters for Ollama models.

        Attributes:
            additional_args: Any additional arguments to include in the request.
            keep_alive: Controls how long the model will stay loaded into memory following the request (default: "5m").
            max_tokens: Maximum number of tokens to generate in the response.
            model_id: Ollama model ID (e.g., "llama3", "mistral", "phi3").
            options: Additional model parameters (e.g., top_k).
            stop_sequences: List of sequences that will stop generation when encountered.
            temperature: Controls randomness in generation (higher = more random).
            top_p: Controls diversity via nucleus sampling (alternative to temperature).
        """

        additional_args: Optional[dict[str, Any]]
        keep_alive: Optional[str]
        max_tokens: Optional[int]
        model_id: str
        options: Optional[dict[str, Any]]
        stop_sequences: Optional[list[str]]
        temperature: Optional[float]
        top_p: Optional[float]

    def __init__(
        self,
        host: Optional[str],
        *,
        ollama_client_args: Optional[dict[str, Any]] = None,
        **model_config: Unpack[OllamaConfig],
    ) -> None:
        """Initialize provider instance.

        Args:
            host: The address of the Ollama server hosting the model.
            ollama_client_args: Additional arguments for the Ollama client.
            **model_config: Configuration options for the Ollama model.
        """
        self.host = host
        self.client_args = ollama_client_args or {}
        self.config = OllamaModel.OllamaConfig(**model_config)

        logger.debug("config=<%s> | initializing", self.config)

    @override
    def update_config(self, **model_config: Unpack[OllamaConfig]) -> None:  # type: ignore
        """Update the Ollama Model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> OllamaConfig:
        """Get the Ollama model configuration.

        Returns:
            The Ollama model configuration.
        """
        return self.config

    def _format_request_message_contents(self, role: str, content: ContentBlock) -> list[dict[str, Any]]:
        """Format Ollama compatible message contents.

        Ollama doesn't support an array of contents, so we must flatten everything into separate message blocks.

        Args:
            role: E.g., user.
            content: Content block to format.

        Returns:
            Ollama formatted message contents.

        Raises:
            TypeError: If the content block type cannot be converted to an Ollama-compatible format.
        """
        if "text" in content:
            return [{"role": role, "content": content["text"]}]

        if "image" in content:
            return [{"role": role, "images": [content["image"]["source"]["bytes"]]}]

        if "toolUse" in content:
            return [
                {
                    "role": role,
                    "tool_calls": [
                        {
                            "function": {
                                "name": content["toolUse"]["toolUseId"],
                                "arguments": content["toolUse"]["input"],
                            }
                        }
                    ],
                }
            ]

        if "toolResult" in content:
            return [
                formatted_tool_result_content
                for tool_result_content in content["toolResult"]["content"]
                for formatted_tool_result_content in self._format_request_message_contents(
                    "tool",
                    (
                        {"text": json.dumps(tool_result_content["json"])}
                        if "json" in tool_result_content
                        else cast(ContentBlock, tool_result_content)
                    ),
                )
            ]

        raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

    def _format_request_messages(self, messages: Messages, system_prompt: Optional[str] = None) -> list[dict[str, Any]]:
        """Format an Ollama compatible messages array.

        Args:
            messages: List of message objects to be processed by the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An Ollama compatible messages array.
        """
        system_message = [{"role": "system", "content": system_prompt}] if system_prompt else []

        return system_message + [
            formatted_message
            for message in messages
            for content in message["content"]
            for formatted_message in self._format_request_message_contents(message["role"], content)
        ]

    def format_request(
        self, messages: Messages, tool_specs: Optional[list[ToolSpec]] = None, system_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        """Format an Ollama chat streaming request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An Ollama chat streaming request.

        Raises:
            TypeError: If a message contains a content block type that cannot be converted to an Ollama-compatible
                format.
        """
        return {
            "messages": self._format_request_messages(messages, system_prompt),
            "model": self.config["model_id"],
            "options": {
                **(self.config.get("options") or {}),
                **{
                    key: value
                    for key, value in [
                        ("num_predict", self.config.get("max_tokens")),
                        ("temperature", self.config.get("temperature")),
                        ("top_p", self.config.get("top_p")),
                        ("stop", self.config.get("stop_sequences")),
                    ]
                    if value is not None
                },
            },
            "stream": True,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool_spec["name"],
                        "description": tool_spec["description"],
                        "parameters": tool_spec["inputSchema"]["json"],
                    },
                }
                for tool_spec in tool_specs or []
            ],
            **({"keep_alive": self.config["keep_alive"]} if self.config.get("keep_alive") else {}),
            **(
                self.config["additional_args"]
                if "additional_args" in self.config and self.config["additional_args"] is not None
                else {}
            ),
        }

    def format_chunk(self, event: dict[str, Any]) -> StreamEvent:
        """Format the Ollama response events into standardized message chunks.

        Args:
            event: A response event from the Ollama model.

        Returns:
            The formatted chunk.

        Raises:
            RuntimeError: If chunk_type is not recognized.
                This error should never be encountered as we control chunk_type in the stream method.
        """
        match event["chunk_type"]:
            case "message_start":
                return {"messageStart": {"role": "assistant"}}

            case "content_start":
                if event["data_type"] == "text":
                    return {"contentBlockStart": {"start": {}}}

                tool_name = event["data"].function.name
                return {"contentBlockStart": {"start": {"toolUse": {"name": tool_name, "toolUseId": tool_name}}}}

            case "content_delta":
                if event["data_type"] == "text":
                    return {"contentBlockDelta": {"delta": {"text": event["data"]}}}

                tool_arguments = event["data"].function.arguments
                return {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_arguments)}}}}

            case "content_stop":
                return {"contentBlockStop": {}}

            case "message_stop":
                reason: StopReason
                if event["data"] == "tool_use":
                    reason = "tool_use"
                elif event["data"] == "length":
                    reason = "max_tokens"
                else:
                    reason = "end_turn"

                return {"messageStop": {"stopReason": reason}}

            case "metadata":
                return {
                    "metadata": {
                        "usage": {
                            "inputTokens": event["data"].eval_count,
                            "outputTokens": event["data"].prompt_eval_count,
                            "totalTokens": event["data"].eval_count + event["data"].prompt_eval_count,
                        },
                        "metrics": {
                            "latencyMs": event["data"].total_duration / 1e6,
                        },
                    },
                }

            case _:
                raise RuntimeError(f"chunk_type=<{event['chunk_type']} | unknown type")

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the Ollama model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("request=<%s>", request)

        logger.debug("invoking model")
        tool_requested = False

        client = ollama.AsyncClient(self.host, **self.client_args)
        response = await client.chat(**request)

        logger.debug("got response from model")
        yield self.format_chunk({"chunk_type": "message_start"})
        yield self.format_chunk({"chunk_type": "content_start", "data_type": "text"})

        async for event in response:
            for tool_call in event.message.tool_calls or []:
                yield self.format_chunk({"chunk_type": "content_start", "data_type": "tool", "data": tool_call})
                yield self.format_chunk({"chunk_type": "content_delta", "data_type": "tool", "data": tool_call})
                yield self.format_chunk({"chunk_type": "content_stop", "data_type": "tool", "data": tool_call})
                tool_requested = True

            yield self.format_chunk({"chunk_type": "content_delta", "data_type": "text", "data": event.message.content})

        yield self.format_chunk({"chunk_type": "content_stop", "data_type": "text"})
        yield self.format_chunk(
            {"chunk_type": "message_stop", "data": "tool_use" if tool_requested else event.done_reason}
        )
        yield self.format_chunk({"chunk_type": "metadata", "data": event})

        logger.debug("finished streaming response from model")

    @override
    async def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events with the last being the structured output.
        """
        formatted_request = self.format_request(messages=prompt, system_prompt=system_prompt)
        formatted_request["format"] = output_model.model_json_schema()
        formatted_request["stream"] = False

        client = ollama.AsyncClient(self.host, **self.client_args)
        response = await client.chat(**formatted_request)

        try:
            content = response.message.content.strip()
            yield {"output": output_model.model_validate_json(content)}
        except Exception as e:
            raise ValueError(f"Failed to parse or load content into model: {e}") from e



================================================
FILE: src/strands/models/openai.py
================================================
"""OpenAI model provider.

- Docs: https://platform.openai.com/docs/overview
"""

import base64
import json
import logging
import mimetypes
from typing import Any, AsyncGenerator, Optional, Protocol, Type, TypedDict, TypeVar, Union, cast

import openai
from openai.types.chat.parsed_chat_completion import ParsedChatCompletion
from pydantic import BaseModel
from typing_extensions import Unpack, override

from ..types.content import ContentBlock, Messages
from ..types.streaming import StreamEvent
from ..types.tools import ToolResult, ToolSpec, ToolUse
from .model import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class Client(Protocol):
    """Protocol defining the OpenAI-compatible interface for the underlying provider client."""

    @property
    # pragma: no cover
    def chat(self) -> Any:
        """Chat completions interface."""
        ...


class OpenAIModel(Model):
    """OpenAI model provider implementation."""

    client: Client

    class OpenAIConfig(TypedDict, total=False):
        """Configuration options for OpenAI models.

        Attributes:
            model_id: Model ID (e.g., "gpt-4o").
                For a complete list of supported models, see https://platform.openai.com/docs/models.
            params: Model parameters (e.g., max_tokens).
                For a complete list of supported parameters, see
                https://platform.openai.com/docs/api-reference/chat/create.
        """

        model_id: str
        params: Optional[dict[str, Any]]

    def __init__(self, client_args: Optional[dict[str, Any]] = None, **model_config: Unpack[OpenAIConfig]) -> None:
        """Initialize provider instance.

        Args:
            client_args: Arguments for the OpenAI client.
                For a complete list of supported arguments, see https://pypi.org/project/openai/.
            **model_config: Configuration options for the OpenAI model.
        """
        self.config = dict(model_config)

        logger.debug("config=<%s> | initializing", self.config)

        client_args = client_args or {}
        self.client = openai.AsyncOpenAI(**client_args)

    @override
    def update_config(self, **model_config: Unpack[OpenAIConfig]) -> None:  # type: ignore[override]
        """Update the OpenAI model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> OpenAIConfig:
        """Get the OpenAI model configuration.

        Returns:
            The OpenAI model configuration.
        """
        return cast(OpenAIModel.OpenAIConfig, self.config)

    @classmethod
    def format_request_message_content(cls, content: ContentBlock) -> dict[str, Any]:
        """Format an OpenAI compatible content block.

        Args:
            content: Message content.

        Returns:
            OpenAI compatible content block.

        Raises:
            TypeError: If the content block type cannot be converted to an OpenAI-compatible format.
        """
        if "document" in content:
            mime_type = mimetypes.types_map.get(f".{content['document']['format']}", "application/octet-stream")
            file_data = base64.b64encode(content["document"]["source"]["bytes"]).decode("utf-8")
            return {
                "file": {
                    "file_data": f"data:{mime_type};base64,{file_data}",
                    "filename": content["document"]["name"],
                },
                "type": "file",
            }

        if "image" in content:
            mime_type = mimetypes.types_map.get(f".{content['image']['format']}", "application/octet-stream")
            image_data = base64.b64encode(content["image"]["source"]["bytes"]).decode("utf-8")

            return {
                "image_url": {
                    "detail": "auto",
                    "format": mime_type,
                    "url": f"data:{mime_type};base64,{image_data}",
                },
                "type": "image_url",
            }

        if "text" in content:
            return {"text": content["text"], "type": "text"}

        raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

    @classmethod
    def format_request_message_tool_call(cls, tool_use: ToolUse) -> dict[str, Any]:
        """Format an OpenAI compatible tool call.

        Args:
            tool_use: Tool use requested by the model.

        Returns:
            OpenAI compatible tool call.
        """
        return {
            "function": {
                "arguments": json.dumps(tool_use["input"]),
                "name": tool_use["name"],
            },
            "id": tool_use["toolUseId"],
            "type": "function",
        }

    @classmethod
    def format_request_tool_message(cls, tool_result: ToolResult) -> dict[str, Any]:
        """Format an OpenAI compatible tool message.

        Args:
            tool_result: Tool result collected from a tool execution.

        Returns:
            OpenAI compatible tool message.
        """
        contents = cast(
            list[ContentBlock],
            [
                {"text": json.dumps(content["json"])} if "json" in content else content
                for content in tool_result["content"]
            ],
        )

        return {
            "role": "tool",
            "tool_call_id": tool_result["toolUseId"],
            "content": [cls.format_request_message_content(content) for content in contents],
        }

    @classmethod
    def format_request_messages(cls, messages: Messages, system_prompt: Optional[str] = None) -> list[dict[str, Any]]:
        """Format an OpenAI compatible messages array.

        Args:
            messages: List of message objects to be processed by the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An OpenAI compatible messages array.
        """
        formatted_messages: list[dict[str, Any]]
        formatted_messages = [{"role": "system", "content": system_prompt}] if system_prompt else []

        for message in messages:
            contents = message["content"]

            formatted_contents = [
                cls.format_request_message_content(content)
                for content in contents
                if not any(block_type in content for block_type in ["toolResult", "toolUse"])
            ]
            formatted_tool_calls = [
                cls.format_request_message_tool_call(content["toolUse"]) for content in contents if "toolUse" in content
            ]
            formatted_tool_messages = [
                cls.format_request_tool_message(content["toolResult"])
                for content in contents
                if "toolResult" in content
            ]

            formatted_message = {
                "role": message["role"],
                "content": formatted_contents,
                **({"tool_calls": formatted_tool_calls} if formatted_tool_calls else {}),
            }
            formatted_messages.append(formatted_message)
            formatted_messages.extend(formatted_tool_messages)

        return [message for message in formatted_messages if message["content"] or "tool_calls" in message]

    def format_request(
        self, messages: Messages, tool_specs: Optional[list[ToolSpec]] = None, system_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        """Format an OpenAI compatible chat streaming request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An OpenAI compatible chat streaming request.

        Raises:
            TypeError: If a message contains a content block type that cannot be converted to an OpenAI-compatible
                format.
        """
        return {
            "messages": self.format_request_messages(messages, system_prompt),
            "model": self.config["model_id"],
            "stream": True,
            "stream_options": {"include_usage": True},
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool_spec["name"],
                        "description": tool_spec["description"],
                        "parameters": tool_spec["inputSchema"]["json"],
                    },
                }
                for tool_spec in tool_specs or []
            ],
            **cast(dict[str, Any], self.config.get("params", {})),
        }

    def format_chunk(self, event: dict[str, Any]) -> StreamEvent:
        """Format an OpenAI response event into a standardized message chunk.

        Args:
            event: A response event from the OpenAI compatible model.

        Returns:
            The formatted chunk.

        Raises:
            RuntimeError: If chunk_type is not recognized.
                This error should never be encountered as chunk_type is controlled in the stream method.
        """
        match event["chunk_type"]:
            case "message_start":
                return {"messageStart": {"role": "assistant"}}

            case "content_start":
                if event["data_type"] == "tool":
                    return {
                        "contentBlockStart": {
                            "start": {
                                "toolUse": {
                                    "name": event["data"].function.name,
                                    "toolUseId": event["data"].id,
                                }
                            }
                        }
                    }

                return {"contentBlockStart": {"start": {}}}

            case "content_delta":
                if event["data_type"] == "tool":
                    return {
                        "contentBlockDelta": {"delta": {"toolUse": {"input": event["data"].function.arguments or ""}}}
                    }

                if event["data_type"] == "reasoning_content":
                    return {"contentBlockDelta": {"delta": {"reasoningContent": {"text": event["data"]}}}}

                return {"contentBlockDelta": {"delta": {"text": event["data"]}}}

            case "content_stop":
                return {"contentBlockStop": {}}

            case "message_stop":
                match event["data"]:
                    case "tool_calls":
                        return {"messageStop": {"stopReason": "tool_use"}}
                    case "length":
                        return {"messageStop": {"stopReason": "max_tokens"}}
                    case _:
                        return {"messageStop": {"stopReason": "end_turn"}}

            case "metadata":
                return {
                    "metadata": {
                        "usage": {
                            "inputTokens": event["data"].prompt_tokens,
                            "outputTokens": event["data"].completion_tokens,
                            "totalTokens": event["data"].total_tokens,
                        },
                        "metrics": {
                            "latencyMs": 0,  # TODO
                        },
                    },
                }

            case _:
                raise RuntimeError(f"chunk_type=<{event['chunk_type']} | unknown type")

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the OpenAI model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("formatted request=<%s>", request)

        logger.debug("invoking model")
        response = await self.client.chat.completions.create(**request)

        logger.debug("got response from model")
        yield self.format_chunk({"chunk_type": "message_start"})
        yield self.format_chunk({"chunk_type": "content_start", "data_type": "text"})

        tool_calls: dict[int, list[Any]] = {}

        async for event in response:
            # Defensive: skip events with empty or missing choices
            if not getattr(event, "choices", None):
                continue
            choice = event.choices[0]

            if choice.delta.content:
                yield self.format_chunk(
                    {"chunk_type": "content_delta", "data_type": "text", "data": choice.delta.content}
                )

            if hasattr(choice.delta, "reasoning_content") and choice.delta.reasoning_content:
                yield self.format_chunk(
                    {
                        "chunk_type": "content_delta",
                        "data_type": "reasoning_content",
                        "data": choice.delta.reasoning_content,
                    }
                )

            for tool_call in choice.delta.tool_calls or []:
                tool_calls.setdefault(tool_call.index, []).append(tool_call)

            if choice.finish_reason:
                break

        yield self.format_chunk({"chunk_type": "content_stop", "data_type": "text"})

        for tool_deltas in tool_calls.values():
            yield self.format_chunk({"chunk_type": "content_start", "data_type": "tool", "data": tool_deltas[0]})

            for tool_delta in tool_deltas:
                yield self.format_chunk({"chunk_type": "content_delta", "data_type": "tool", "data": tool_delta})

            yield self.format_chunk({"chunk_type": "content_stop", "data_type": "tool"})

        yield self.format_chunk({"chunk_type": "message_stop", "data": choice.finish_reason})

        # Skip remaining events as we don't have use for anything except the final usage payload
        async for event in response:
            _ = event

        if event.usage:
            yield self.format_chunk({"chunk_type": "metadata", "data": event.usage})

        logger.debug("finished streaming response from model")

    @override
    async def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events with the last being the structured output.
        """
        response: ParsedChatCompletion = await self.client.beta.chat.completions.parse(  # type: ignore
            model=self.get_config()["model_id"],
            messages=self.format_request(prompt, system_prompt=system_prompt)["messages"],
            response_format=output_model,
        )

        parsed: T | None = None
        # Find the first choice with tool_calls
        if len(response.choices) > 1:
            raise ValueError("Multiple choices found in the OpenAI response.")

        for choice in response.choices:
            if isinstance(choice.message.parsed, output_model):
                parsed = choice.message.parsed
                break

        if parsed:
            yield {"output": parsed}
        else:
            raise ValueError("No valid tool use or tool use input was found in the OpenAI response.")



================================================
FILE: src/strands/models/sagemaker.py
================================================
"""Amazon SageMaker model provider."""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal, Optional, Type, TypedDict, TypeVar, Union, cast

import boto3
from botocore.config import Config as BotocoreConfig
from mypy_boto3_sagemaker_runtime import SageMakerRuntimeClient
from pydantic import BaseModel
from typing_extensions import Unpack, override

from ..types.content import ContentBlock, Messages
from ..types.streaming import StreamEvent
from ..types.tools import ToolResult, ToolSpec
from .openai import OpenAIModel

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


@dataclass
class UsageMetadata:
    """Usage metadata for the model.

    Attributes:
        total_tokens: Total number of tokens used in the request
        completion_tokens: Number of tokens used in the completion
        prompt_tokens: Number of tokens used in the prompt
        prompt_tokens_details: Additional information about the prompt tokens (optional)
    """

    total_tokens: int
    completion_tokens: int
    prompt_tokens: int
    prompt_tokens_details: Optional[int] = 0


@dataclass
class FunctionCall:
    """Function call for the model.

    Attributes:
        name: Name of the function to call
        arguments: Arguments to pass to the function
    """

    name: Union[str, dict[Any, Any]]
    arguments: Union[str, dict[Any, Any]]

    def __init__(self, **kwargs: dict[str, str]):
        """Initialize function call.

        Args:
            **kwargs: Keyword arguments for the function call.
        """
        self.name = kwargs.get("name", "")
        self.arguments = kwargs.get("arguments", "")


@dataclass
class ToolCall:
    """Tool call for the model object.

    Attributes:
        id: Tool call ID
        type: Tool call type
        function: Tool call function
    """

    id: str
    type: Literal["function"]
    function: FunctionCall

    def __init__(self, **kwargs: dict):
        """Initialize tool call object.

        Args:
            **kwargs: Keyword arguments for the tool call.
        """
        self.id = str(kwargs.get("id", ""))
        self.type = "function"
        self.function = FunctionCall(**kwargs.get("function", {"name": "", "arguments": ""}))


class SageMakerAIModel(OpenAIModel):
    """Amazon SageMaker model provider implementation."""

    client: SageMakerRuntimeClient  # type: ignore[assignment]

    class SageMakerAIPayloadSchema(TypedDict, total=False):
        """Payload schema for the Amazon SageMaker AI model.

        Attributes:
            max_tokens: Maximum number of tokens to generate in the completion
            stream: Whether to stream the response
            temperature: Sampling temperature to use for the model (optional)
            top_p: Nucleus sampling parameter (optional)
            top_k: Top-k sampling parameter (optional)
            stop: List of stop sequences to use for the model (optional)
            tool_results_as_user_messages: Convert tool result to user messages (optional)
            additional_args: Additional request parameters, as supported by https://bit.ly/djl-lmi-request-schema
        """

        max_tokens: int
        stream: bool
        temperature: Optional[float]
        top_p: Optional[float]
        top_k: Optional[int]
        stop: Optional[list[str]]
        tool_results_as_user_messages: Optional[bool]
        additional_args: Optional[dict[str, Any]]

    class SageMakerAIEndpointConfig(TypedDict, total=False):
        """Configuration options for SageMaker models.

        Attributes:
            endpoint_name: The name of the SageMaker endpoint to invoke
            inference_component_name: The name of the inference component to use

            additional_args: Other request parameters, as supported by https://bit.ly/sagemaker-invoke-endpoint-params
        """

        endpoint_name: str
        region_name: str
        inference_component_name: Union[str, None]
        target_model: Union[Optional[str], None]
        target_variant: Union[Optional[str], None]
        additional_args: Optional[dict[str, Any]]

    def __init__(
        self,
        endpoint_config: SageMakerAIEndpointConfig,
        payload_config: SageMakerAIPayloadSchema,
        boto_session: Optional[boto3.Session] = None,
        boto_client_config: Optional[BotocoreConfig] = None,
    ):
        """Initialize provider instance.

        Args:
            endpoint_config: Endpoint configuration for SageMaker.
            payload_config: Payload configuration for the model.
            boto_session: Boto Session to use when calling the SageMaker Runtime.
            boto_client_config: Configuration to use when creating the SageMaker-Runtime Boto Client.
        """
        payload_config.setdefault("stream", True)
        payload_config.setdefault("tool_results_as_user_messages", False)
        self.endpoint_config = dict(endpoint_config)
        self.payload_config = dict(payload_config)
        logger.debug(
            "endpoint_config=<%s> payload_config=<%s> | initializing", self.endpoint_config, self.payload_config
        )

        region = self.endpoint_config.get("region_name") or os.getenv("AWS_REGION") or "us-west-2"
        session = boto_session or boto3.Session(region_name=str(region))

        # Add strands-agents to the request user agent
        if boto_client_config:
            existing_user_agent = getattr(boto_client_config, "user_agent_extra", None)

            # Append 'strands-agents' to existing user_agent_extra or set it if not present
            new_user_agent = f"{existing_user_agent} strands-agents" if existing_user_agent else "strands-agents"

            client_config = boto_client_config.merge(BotocoreConfig(user_agent_extra=new_user_agent))
        else:
            client_config = BotocoreConfig(user_agent_extra="strands-agents")

        self.client = session.client(
            service_name="sagemaker-runtime",
            config=client_config,
        )

    @override
    def update_config(self, **endpoint_config: Unpack[SageMakerAIEndpointConfig]) -> None:  # type: ignore[override]
        """Update the Amazon SageMaker model configuration with the provided arguments.

        Args:
            **endpoint_config: Configuration overrides.
        """
        self.endpoint_config.update(endpoint_config)

    @override
    def get_config(self) -> "SageMakerAIModel.SageMakerAIEndpointConfig":  # type: ignore[override]
        """Get the Amazon SageMaker model configuration.

        Returns:
            The Amazon SageMaker model configuration.
        """
        return cast(SageMakerAIModel.SageMakerAIEndpointConfig, self.endpoint_config)

    @override
    def format_request(
        self, messages: Messages, tool_specs: Optional[list[ToolSpec]] = None, system_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        """Format an Amazon SageMaker chat streaming request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An Amazon SageMaker chat streaming request.
        """
        formatted_messages = self.format_request_messages(messages, system_prompt)

        payload = {
            "messages": formatted_messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool_spec["name"],
                        "description": tool_spec["description"],
                        "parameters": tool_spec["inputSchema"]["json"],
                    },
                }
                for tool_spec in tool_specs or []
            ],
            # Add payload configuration parameters
            **{
                k: v
                for k, v in self.payload_config.items()
                if k not in ["additional_args", "tool_results_as_user_messages"]
            },
        }

        # Remove tools and tool_choice if tools = []
        if not payload["tools"]:
            payload.pop("tools")
            payload.pop("tool_choice", None)
        else:
            # Ensure the model can use tools when available
            payload["tool_choice"] = "auto"

        for message in payload["messages"]:  # type: ignore
            # Assistant message must have either content or tool_calls, but not both
            if message.get("role", "") == "assistant" and message.get("tool_calls", []) != []:
                message.pop("content", None)
            if message.get("role") == "tool" and self.payload_config.get("tool_results_as_user_messages", False):
                # Convert tool message to user message
                tool_call_id = message.get("tool_call_id", "ABCDEF")
                content = message.get("content", "")
                message = {"role": "user", "content": f"Tool call ID '{tool_call_id}' returned: {content}"}
            # Cannot have both reasoning_text and text - if "text", content becomes an array of content["text"]
            for c in message.get("content", []):
                if "text" in c:
                    message["content"] = [c]
                    break
            # Cast message content to string for TGI compatibility
            # message["content"] = str(message.get("content", ""))

        logger.info("payload=<%s>", json.dumps(payload, indent=2))
        # Format the request according to the SageMaker Runtime API requirements
        request = {
            "EndpointName": self.endpoint_config["endpoint_name"],
            "Body": json.dumps(payload),
            "ContentType": "application/json",
            "Accept": "application/json",
        }

        # Add optional SageMaker parameters if provided
        if self.endpoint_config.get("inference_component_name"):
            request["InferenceComponentName"] = self.endpoint_config["inference_component_name"]
        if self.endpoint_config.get("target_model"):
            request["TargetModel"] = self.endpoint_config["target_model"]
        if self.endpoint_config.get("target_variant"):
            request["TargetVariant"] = self.endpoint_config["target_variant"]

        # Add additional args if provided
        if self.endpoint_config.get("additional_args"):
            request.update(self.endpoint_config["additional_args"].__dict__)

        return request

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the SageMaker model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("formatted request=<%s>", request)

        logger.debug("invoking model")
        try:
            if self.payload_config.get("stream", True):
                response = self.client.invoke_endpoint_with_response_stream(**request)

                # Message start
                yield self.format_chunk({"chunk_type": "message_start"})

                # Parse the content
                finish_reason = ""
                partial_content = ""
                tool_calls: dict[int, list[Any]] = {}
                has_text_content = False
                text_content_started = False
                reasoning_content_started = False

                for event in response["Body"]:
                    chunk = event["PayloadPart"]["Bytes"].decode("utf-8")
                    partial_content += chunk[6:] if chunk.startswith("data: ") else chunk  # TGI fix
                    logger.info("chunk=<%s>", partial_content)
                    try:
                        content = json.loads(partial_content)
                        partial_content = ""
                        choice = content["choices"][0]
                        logger.info("choice=<%s>", json.dumps(choice, indent=2))

                        # Handle text content
                        if choice["delta"].get("content", None):
                            if not text_content_started:
                                yield self.format_chunk({"chunk_type": "content_start", "data_type": "text"})
                                text_content_started = True
                            has_text_content = True
                            yield self.format_chunk(
                                {
                                    "chunk_type": "content_delta",
                                    "data_type": "text",
                                    "data": choice["delta"]["content"],
                                }
                            )

                        # Handle reasoning content
                        if choice["delta"].get("reasoning_content", None):
                            if not reasoning_content_started:
                                yield self.format_chunk(
                                    {"chunk_type": "content_start", "data_type": "reasoning_content"}
                                )
                                reasoning_content_started = True
                            yield self.format_chunk(
                                {
                                    "chunk_type": "content_delta",
                                    "data_type": "reasoning_content",
                                    "data": choice["delta"]["reasoning_content"],
                                }
                            )

                        # Handle tool calls
                        generated_tool_calls = choice["delta"].get("tool_calls", [])
                        if not isinstance(generated_tool_calls, list):
                            generated_tool_calls = [generated_tool_calls]
                        for tool_call in generated_tool_calls:
                            tool_calls.setdefault(tool_call["index"], []).append(tool_call)

                        if choice["finish_reason"] is not None:
                            finish_reason = choice["finish_reason"]
                            break

                        if choice.get("usage", None):
                            yield self.format_chunk(
                                {"chunk_type": "metadata", "data": UsageMetadata(**choice["usage"])}
                            )

                    except json.JSONDecodeError:
                        # Continue accumulating content until we have valid JSON
                        continue

                # Close reasoning content if it was started
                if reasoning_content_started:
                    yield self.format_chunk({"chunk_type": "content_stop", "data_type": "reasoning_content"})

                # Close text content if it was started
                if text_content_started:
                    yield self.format_chunk({"chunk_type": "content_stop", "data_type": "text"})

                # Handle tool calling
                logger.info("tool_calls=<%s>", json.dumps(tool_calls, indent=2))
                for tool_deltas in tool_calls.values():
                    if not tool_deltas[0]["function"].get("name", None):
                        raise Exception("The model did not provide a tool name.")
                    yield self.format_chunk(
                        {"chunk_type": "content_start", "data_type": "tool", "data": ToolCall(**tool_deltas[0])}
                    )
                    for tool_delta in tool_deltas:
                        yield self.format_chunk(
                            {"chunk_type": "content_delta", "data_type": "tool", "data": ToolCall(**tool_delta)}
                        )
                    yield self.format_chunk({"chunk_type": "content_stop", "data_type": "tool"})

                # If no content was generated at all, ensure we have empty text content
                if not has_text_content and not tool_calls:
                    yield self.format_chunk({"chunk_type": "content_start", "data_type": "text"})
                    yield self.format_chunk({"chunk_type": "content_stop", "data_type": "text"})

                # Message close
                yield self.format_chunk({"chunk_type": "message_stop", "data": finish_reason})

            else:
                # Not all SageMaker AI models support streaming!
                response = self.client.invoke_endpoint(**request)  # type: ignore[assignment]
                final_response_json = json.loads(response["Body"].read().decode("utf-8"))  # type: ignore[attr-defined]
                logger.info("response=<%s>", json.dumps(final_response_json, indent=2))

                # Obtain the key elements from the response
                message = final_response_json["choices"][0]["message"]
                message_stop_reason = final_response_json["choices"][0]["finish_reason"]

                # Message start
                yield self.format_chunk({"chunk_type": "message_start"})

                # Handle text
                if message.get("content", ""):
                    yield self.format_chunk({"chunk_type": "content_start", "data_type": "text"})
                    yield self.format_chunk(
                        {"chunk_type": "content_delta", "data_type": "text", "data": message["content"]}
                    )
                    yield self.format_chunk({"chunk_type": "content_stop", "data_type": "text"})

                # Handle reasoning content
                if message.get("reasoning_content", None):
                    yield self.format_chunk({"chunk_type": "content_start", "data_type": "reasoning_content"})
                    yield self.format_chunk(
                        {
                            "chunk_type": "content_delta",
                            "data_type": "reasoning_content",
                            "data": message["reasoning_content"],
                        }
                    )
                    yield self.format_chunk({"chunk_type": "content_stop", "data_type": "reasoning_content"})

                # Handle the tool calling, if any
                if message.get("tool_calls", None) or message_stop_reason == "tool_calls":
                    if not isinstance(message["tool_calls"], list):
                        message["tool_calls"] = [message["tool_calls"]]
                    for tool_call in message["tool_calls"]:
                        # if arguments of tool_call is not str, cast it
                        if not isinstance(tool_call["function"]["arguments"], str):
                            tool_call["function"]["arguments"] = json.dumps(tool_call["function"]["arguments"])
                        yield self.format_chunk(
                            {"chunk_type": "content_start", "data_type": "tool", "data": ToolCall(**tool_call)}
                        )
                        yield self.format_chunk(
                            {"chunk_type": "content_delta", "data_type": "tool", "data": ToolCall(**tool_call)}
                        )
                        yield self.format_chunk({"chunk_type": "content_stop", "data_type": "tool"})
                    message_stop_reason = "tool_calls"

                # Message close
                yield self.format_chunk({"chunk_type": "message_stop", "data": message_stop_reason})
                # Handle usage metadata
                if final_response_json.get("usage", None):
                    yield self.format_chunk(
                        {"chunk_type": "metadata", "data": UsageMetadata(**final_response_json.get("usage", None))}
                    )
        except (
            self.client.exceptions.InternalFailure,
            self.client.exceptions.ServiceUnavailable,
            self.client.exceptions.ValidationError,
            self.client.exceptions.ModelError,
            self.client.exceptions.InternalDependencyException,
            self.client.exceptions.ModelNotReadyException,
        ) as e:
            logger.error("SageMaker error: %s", str(e))
            raise e

        logger.debug("finished streaming response from model")

    @override
    @classmethod
    def format_request_tool_message(cls, tool_result: ToolResult) -> dict[str, Any]:
        """Format a SageMaker compatible tool message.

        Args:
            tool_result: Tool result collected from a tool execution.

        Returns:
            SageMaker compatible tool message with content as a string.
        """
        # Convert content blocks to a simple string for SageMaker compatibility
        content_parts = []
        for content in tool_result["content"]:
            if "json" in content:
                content_parts.append(json.dumps(content["json"]))
            elif "text" in content:
                content_parts.append(content["text"])
            else:
                # Handle other content types by converting to string
                content_parts.append(str(content))

        content_string = " ".join(content_parts)

        return {
            "role": "tool",
            "tool_call_id": tool_result["toolUseId"],
            "content": content_string,  # String instead of list
        }

    @override
    @classmethod
    def format_request_message_content(cls, content: ContentBlock) -> dict[str, Any]:
        """Format a content block.

        Args:
            content: Message content.

        Returns:
            Formatted content block.

        Raises:
            TypeError: If the content block type cannot be converted to a SageMaker-compatible format.
        """
        # if "text" in content and not isinstance(content["text"], str):
        #     return {"type": "text", "text": str(content["text"])}

        if "reasoningContent" in content and content["reasoningContent"]:
            return {
                "signature": content["reasoningContent"].get("reasoningText", {}).get("signature", ""),
                "thinking": content["reasoningContent"].get("reasoningText", {}).get("text", ""),
                "type": "thinking",
            }
        elif not content.get("reasoningContent", None):
            content.pop("reasoningContent", None)

        if "video" in content:
            return {
                "type": "video_url",
                "video_url": {
                    "detail": "auto",
                    "url": content["video"]["source"]["bytes"],
                },
            }

        return super().format_request_message_content(content)

    @override
    async def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Model events with the last being the structured output.
        """
        # Format the request for structured output
        request = self.format_request(prompt, system_prompt=system_prompt)

        # Parse the payload to add response format
        payload = json.loads(request["Body"])
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": output_model.__name__, "schema": output_model.model_json_schema(), "strict": True},
        }
        request["Body"] = json.dumps(payload)

        try:
            # Use non-streaming mode for structured output
            response = self.client.invoke_endpoint(**request)
            final_response_json = json.loads(response["Body"].read().decode("utf-8"))

            # Extract the structured content
            message = final_response_json["choices"][0]["message"]

            if message.get("content"):
                try:
                    # Parse the JSON content and create the output model instance
                    content_data = json.loads(message["content"])
                    parsed_output = output_model(**content_data)
                    yield {"output": parsed_output}
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    raise ValueError(f"Failed to parse structured output: {e}") from e
            else:
                raise ValueError("No content found in SageMaker response")

        except (
            self.client.exceptions.InternalFailure,
            self.client.exceptions.ServiceUnavailable,
            self.client.exceptions.ValidationError,
            self.client.exceptions.ModelError,
            self.client.exceptions.InternalDependencyException,
            self.client.exceptions.ModelNotReadyException,
        ) as e:
            logger.error("SageMaker structured output error: %s", str(e))
            raise ValueError(f"SageMaker structured output error: {str(e)}") from e



================================================
FILE: src/strands/models/writer.py
================================================
"""Writer model provider.

- Docs: https://dev.writer.com/home/introduction
"""

import base64
import json
import logging
import mimetypes
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, TypedDict, TypeVar, Union, cast

import writerai
from pydantic import BaseModel
from typing_extensions import Unpack, override

from ..types.content import ContentBlock, Messages
from ..types.exceptions import ModelThrottledException
from ..types.streaming import StreamEvent
from ..types.tools import ToolResult, ToolSpec, ToolUse
from .model import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class WriterModel(Model):
    """Writer API model provider implementation."""

    class WriterConfig(TypedDict, total=False):
        """Configuration options for Writer API.

        Attributes:
            model_id: Model name to use (e.g. palmyra-x5, palmyra-x4, etc.).
            max_tokens: Maximum number of tokens to generate.
            stop: Default stop sequences.
            stream_options: Additional options for streaming.
            temperature: What sampling temperature to use.
            top_p: Threshold for 'nucleus sampling'
        """

        model_id: str
        max_tokens: Optional[int]
        stop: Optional[Union[str, List[str]]]
        stream_options: Dict[str, Any]
        temperature: Optional[float]
        top_p: Optional[float]

    def __init__(self, client_args: Optional[dict[str, Any]] = None, **model_config: Unpack[WriterConfig]):
        """Initialize provider instance.

        Args:
            client_args: Arguments for the Writer client (e.g., api_key, base_url, timeout, etc.).
            **model_config: Configuration options for the Writer model.
        """
        self.config = WriterModel.WriterConfig(**model_config)

        logger.debug("config=<%s> | initializing", self.config)

        client_args = client_args or {}
        self.client = writerai.AsyncClient(**client_args)

    @override
    def update_config(self, **model_config: Unpack[WriterConfig]) -> None:  # type: ignore[override]
        """Update the Writer Model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> WriterConfig:
        """Get the Writer model configuration.

        Returns:
            The Writer model configuration.
        """
        return self.config

    def _format_request_message_contents_vision(self, contents: list[ContentBlock]) -> list[dict[str, Any]]:
        def _format_content_vision(content: ContentBlock) -> dict[str, Any]:
            """Format a Writer content block for Palmyra V5 request.

            - NOTE: "reasoningContent", "document" and "video" are not supported currently.

            Args:
                content: Message content.

            Returns:
                Writer formatted content block for models, which support vision content format.

            Raises:
                TypeError: If the content block type cannot be converted to a Writer-compatible format.
            """
            if "text" in content:
                return {"text": content["text"], "type": "text"}

            if "image" in content:
                mime_type = mimetypes.types_map.get(f".{content['image']['format']}", "application/octet-stream")
                image_data = base64.b64encode(content["image"]["source"]["bytes"]).decode("utf-8")

                return {
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_data}",
                    },
                    "type": "image_url",
                }

            raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

        return [
            _format_content_vision(content)
            for content in contents
            if not any(block_type in content for block_type in ["toolResult", "toolUse"])
        ]

    def _format_request_message_contents(self, contents: list[ContentBlock]) -> str:
        def _format_content(content: ContentBlock) -> str:
            """Format a Writer content block for Palmyra models (except V5) request.

            - NOTE: "reasoningContent", "document", "video" and "image" are not supported currently.

            Args:
                content: Message content.

            Returns:
                Writer formatted content block.

            Raises:
                TypeError: If the content block type cannot be converted to a Writer-compatible format.
            """
            if "text" in content:
                return content["text"]

            raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

        content_blocks = list(
            filter(
                lambda content: content.get("text")
                and not any(block_type in content for block_type in ["toolResult", "toolUse"]),
                contents,
            )
        )

        if len(content_blocks) > 1:
            raise ValueError(
                f"Model with name {self.get_config().get('model_id', 'N/A')} doesn't support multiple contents"
            )
        elif len(content_blocks) == 1:
            return _format_content(content_blocks[0])
        else:
            return ""

    def _format_request_message_tool_call(self, tool_use: ToolUse) -> dict[str, Any]:
        """Format a Writer tool call.

        Args:
            tool_use: Tool use requested by the model.

        Returns:
            Writer formatted tool call.
        """
        return {
            "function": {
                "arguments": json.dumps(tool_use["input"]),
                "name": tool_use["name"],
            },
            "id": tool_use["toolUseId"],
            "type": "function",
        }

    def _format_request_tool_message(self, tool_result: ToolResult) -> dict[str, Any]:
        """Format a Writer tool message.

        Args:
            tool_result: Tool result collected from a tool execution.

        Returns:
            Writer formatted tool message.
        """
        contents = cast(
            list[ContentBlock],
            [
                {"text": json.dumps(content["json"])} if "json" in content else content
                for content in tool_result["content"]
            ],
        )

        if self.get_config().get("model_id", "") == "palmyra-x5":
            formatted_contents = self._format_request_message_contents_vision(contents)
        else:
            formatted_contents = self._format_request_message_contents(contents)  # type: ignore [assignment]

        return {
            "role": "tool",
            "tool_call_id": tool_result["toolUseId"],
            "content": formatted_contents,
        }

    def _format_request_messages(self, messages: Messages, system_prompt: Optional[str] = None) -> list[dict[str, Any]]:
        """Format a Writer compatible messages array.

        Args:
            messages: List of message objects to be processed by the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            Writer compatible messages array.
        """
        formatted_messages: list[dict[str, Any]]
        formatted_messages = [{"role": "system", "content": system_prompt}] if system_prompt else []

        for message in messages:
            contents = message["content"]

            # Only palmyra V5 support multiple content. Other models support only '{"content": "text_content"}'
            if self.get_config().get("model_id", "") == "palmyra-x5":
                formatted_contents: str | list[dict[str, Any]] = self._format_request_message_contents_vision(contents)
            else:
                formatted_contents = self._format_request_message_contents(contents)

            formatted_tool_calls = [
                self._format_request_message_tool_call(content["toolUse"])
                for content in contents
                if "toolUse" in content
            ]
            formatted_tool_messages = [
                self._format_request_tool_message(content["toolResult"])
                for content in contents
                if "toolResult" in content
            ]

            formatted_message = {
                "role": message["role"],
                "content": formatted_contents if len(formatted_contents) > 0 else "",
                **({"tool_calls": formatted_tool_calls} if formatted_tool_calls else {}),
            }
            formatted_messages.append(formatted_message)
            formatted_messages.extend(formatted_tool_messages)

        return [message for message in formatted_messages if message["content"] or "tool_calls" in message]

    def format_request(
        self, messages: Messages, tool_specs: Optional[list[ToolSpec]] = None, system_prompt: Optional[str] = None
    ) -> Any:
        """Format a streaming request to the underlying model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            The formatted request.
        """
        request = {
            **{k: v for k, v in self.config.items()},
            "messages": self._format_request_messages(messages, system_prompt),
            "stream": True,
        }
        try:
            request["model"] = request.pop(
                "model_id"
            )  # To be consisted with other models WriterConfig use 'model_id' arg, but Writer API wait for 'model' arg
        except KeyError as e:
            raise KeyError("Please specify a model ID. Use 'model_id' keyword argument.") from e

        # Writer don't support empty tools attribute
        if tool_specs:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool_spec["name"],
                        "description": tool_spec["description"],
                        "parameters": tool_spec["inputSchema"]["json"],
                    },
                }
                for tool_spec in tool_specs
            ]

        return request

    def format_chunk(self, event: Any) -> StreamEvent:
        """Format the model response events into standardized message chunks.

        Args:
            event: A response event from the model.

        Returns:
            The formatted chunk.
        """
        match event.get("chunk_type", ""):
            case "message_start":
                return {"messageStart": {"role": "assistant"}}

            case "content_block_start":
                if event["data_type"] == "text":
                    return {"contentBlockStart": {"start": {}}}

                return {
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "name": event["data"].function.name,
                                "toolUseId": event["data"].id,
                            }
                        }
                    }
                }

            case "content_block_delta":
                if event["data_type"] == "text":
                    return {"contentBlockDelta": {"delta": {"text": event["data"]}}}

                return {"contentBlockDelta": {"delta": {"toolUse": {"input": event["data"].function.arguments}}}}

            case "content_block_stop":
                return {"contentBlockStop": {}}

            case "message_stop":
                match event["data"]:
                    case "tool_calls":
                        return {"messageStop": {"stopReason": "tool_use"}}
                    case "length":
                        return {"messageStop": {"stopReason": "max_tokens"}}
                    case _:
                        return {"messageStop": {"stopReason": "end_turn"}}

            case "metadata":
                return {
                    "metadata": {
                        "usage": {
                            "inputTokens": event["data"].prompt_tokens if event["data"] else 0,
                            "outputTokens": event["data"].completion_tokens if event["data"] else 0,
                            "totalTokens": event["data"].total_tokens if event["data"] else 0,
                        },  # If 'stream_options' param is unset, empty metadata will be provided.
                        # To avoid errors replacing expected fields with default zero value
                        "metrics": {
                            "latencyMs": 0,  # All palmyra models don't provide 'latency' metadata
                        },
                    },
                }

            case _:
                raise RuntimeError(f"chunk_type=<{event['chunk_type']} | unknown type")

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the Writer model.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.

        Yields:
            Formatted message chunks from the model.

        Raises:
            ModelThrottledException: When the model service is throttling requests from the client.
        """
        logger.debug("formatting request")
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("request=<%s>", request)

        logger.debug("invoking model")
        try:
            response = await self.client.chat.chat(**request)
        except writerai.RateLimitError as e:
            raise ModelThrottledException(str(e)) from e

        yield self.format_chunk({"chunk_type": "message_start"})
        yield self.format_chunk({"chunk_type": "content_block_start", "data_type": "text"})

        tool_calls: dict[int, list[Any]] = {}

        async for chunk in response:
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]

            if choice.delta.content:
                yield self.format_chunk(
                    {"chunk_type": "content_block_delta", "data_type": "text", "data": choice.delta.content}
                )

            for tool_call in choice.delta.tool_calls or []:
                tool_calls.setdefault(tool_call.index, []).append(tool_call)

            if choice.finish_reason:
                break

        yield self.format_chunk({"chunk_type": "content_block_stop", "data_type": "text"})

        for tool_deltas in tool_calls.values():
            tool_start, tool_deltas = tool_deltas[0], tool_deltas[1:]
            yield self.format_chunk({"chunk_type": "content_block_start", "data_type": "tool", "data": tool_start})

            for tool_delta in tool_deltas:
                yield self.format_chunk({"chunk_type": "content_block_delta", "data_type": "tool", "data": tool_delta})

            yield self.format_chunk({"chunk_type": "content_block_stop", "data_type": "tool"})

        yield self.format_chunk({"chunk_type": "message_stop", "data": choice.finish_reason})

        # Iterating until the end to fetch metadata chunk
        async for chunk in response:
            _ = chunk

        yield self.format_chunk({"chunk_type": "metadata", "data": chunk.usage})

        logger.debug("finished streaming response from model")

    @override
    async def structured_output(
        self, output_model: Type[T], prompt: Messages, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.

        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.
        """
        formatted_request = self.format_request(messages=prompt, tool_specs=None, system_prompt=system_prompt)
        formatted_request["response_format"] = {
            "type": "json_schema",
            "json_schema": {"schema": output_model.model_json_schema()},
        }
        formatted_request["stream"] = False
        formatted_request.pop("stream_options", None)

        response = await self.client.chat.chat(**formatted_request)

        try:
            content = response.choices[0].message.content.strip()
            yield {"output": output_model.model_validate_json(content)}
        except Exception as e:
            raise ValueError(f"Failed to parse or load content into model: {e}") from e

