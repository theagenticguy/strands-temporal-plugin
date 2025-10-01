"""Test script to debug Pydantic serialization issue."""

import sys

sys.path.insert(0, "src")

from strands_temporal_plugin import BedrockProviderConfig, EchoProviderConfig
from strands_temporal_plugin.pydantic_converter import PydanticJSONPlainPayloadConverter, ToJsonOptions
import temporalio.api.common.v1
import json

# Create a Bedrock config
bedrock_config = BedrockProviderConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region="us-east-1")

print("Original config:")
print(f"  Type: {type(bedrock_config)}")
print(f"  Data: {bedrock_config}")
print(f"  Model dump: {bedrock_config.model_dump()}")

# Test serialization with the custom converter
converter = PydanticJSONPlainPayloadConverter()

# Serialize
payload = converter.to_payload(bedrock_config)
print("\nSerialized payload:")
print(f"  Metadata: {payload.metadata}")
print(f"  Data: {payload.data}")
print(f"  Data decoded: {json.loads(payload.data)}")

# Deserialize without type hint (what happens in activities)
from strands_temporal_plugin.types import ProviderConfig

deserialized = converter.from_payload(payload, ProviderConfig)
print("\nDeserialized with ProviderConfig type hint:")
print(f"  Type: {type(deserialized)}")
print(f"  Data: {deserialized}")
if hasattr(deserialized, "model_dump"):
    print(f"  Model dump: {deserialized.model_dump()}")

# Deserialize with correct type hint
deserialized_correct = converter.from_payload(payload, BedrockProviderConfig)
print("\nDeserialized with BedrockProviderConfig type hint:")
print(f"  Type: {type(deserialized_correct)}")
print(f"  Data: {deserialized_correct}")
print(f"  Model dump: {deserialized_correct.model_dump()}")
