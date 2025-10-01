"""Simple test to debug the provider configuration issue."""

import sys

sys.path.insert(0, "src")

from strands_temporal_plugin.types import BedrockProviderConfig, EchoProviderConfig, ProviderConfig, ModelCallInput
import json

# Create a Bedrock config
bedrock_config = BedrockProviderConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region="us-east-1")

print("1. Original BedrockProviderConfig:")
print(f"   Type: {type(bedrock_config)}")
print(f"   Data: {bedrock_config}")
print(f"   model_dump(): {bedrock_config.model_dump()}")

# Test what happens when we assign to ProviderConfig type
provider_config: ProviderConfig = bedrock_config
print(f"\n2. Assigned to ProviderConfig type:")
print(f"   Type: {type(provider_config)}")
print(f"   Data: {provider_config}")
print(f"   model_dump(): {provider_config.model_dump()}")

# Create ModelCallInput with this provider
model_input = ModelCallInput(messages=[], provider=bedrock_config)
print(f"\n3. ModelCallInput with provider:")
print(f"   Type: {type(model_input.provider)}")
print(f"   Data: {model_input.provider}")
print(f"   model_dump(): {model_input.model_dump()}")

# Test serialization to dict and back
serialized = model_input.model_dump()
print(f"\n4. Serialized ModelCallInput:")
print(f"   Full: {serialized}")
print(f"   Provider part: {serialized['provider']}")

# Try to recreate from dict
try:
    recreated = ModelCallInput(**serialized)
    print(f"\n5. Recreated from dict:")
    print(f"   Provider type: {type(recreated.provider)}")
    print(f"   Provider data: {recreated.provider}")
    if hasattr(recreated.provider, "model_dump"):
        print(f"   Provider model_dump(): {recreated.provider.model_dump()}")
except Exception as e:
    print(f"\n5. ERROR recreating from dict: {e}")

# Test what happens with JSON round-trip
json_str = json.dumps(serialized)
json_data = json.loads(json_str)
print(f"\n6. JSON round-trip:")
print(f"   JSON provider: {json_data['provider']}")

try:
    recreated_from_json = ModelCallInput(**json_data)
    print(f"   Recreated provider type: {type(recreated_from_json.provider)}")
    print(f"   Recreated provider data: {recreated_from_json.provider}")
    if hasattr(recreated_from_json.provider, "model_dump"):
        print(f"   Recreated provider model_dump(): {recreated_from_json.provider.model_dump()}")
except Exception as e:
    print(f"   ERROR recreating from JSON: {e}")
