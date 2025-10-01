"""Minimal test to debug the provider configuration issue."""

import sys

sys.path.insert(0, "src")

# Import directly from types.py to avoid temporalio imports
import importlib.util

spec = importlib.util.spec_from_file_location("types", "src/strands_temporal_plugin/types.py")
types_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(types_module)

BedrockProviderConfig = types_module.BedrockProviderConfig
EchoProviderConfig = types_module.EchoProviderConfig
ProviderConfig = types_module.ProviderConfig
ModelCallInput = types_module.ModelCallInput
import json

# Create a Bedrock config
bedrock_config = BedrockProviderConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region="us-east-1")

print("1. Original BedrockProviderConfig:")
print(f"   Type: {type(bedrock_config)}")
print(f"   Data: {bedrock_config}")
print(f"   model_dump(): {bedrock_config.model_dump()}")

# Test serialization to dict and back
serialized = bedrock_config.model_dump()
print(f"\n2. Serialized BedrockProviderConfig:")
print(f"   Data: {serialized}")

# Test what happens with JSON round-trip
json_str = json.dumps(serialized)
json_data = json.loads(json_str)
print(f"\n3. JSON round-trip:")
print(f"   JSON data: {json_data}")

# Try to recreate BedrockProviderConfig from dict
try:
    recreated = BedrockProviderConfig(**json_data)
    print(f"\n4. Recreated BedrockProviderConfig from dict:")
    print(f"   Type: {type(recreated)}")
    print(f"   Data: {recreated}")
    print(f"   model_dump(): {recreated.model_dump()}")
except Exception as e:
    print(f"\n4. ERROR recreating BedrockProviderConfig from dict: {e}")

# Try to create ProviderConfig from dict (what happens in deserialization)
try:
    provider_from_dict = ProviderConfig(**json_data)
    print(f"\n5. ProviderConfig from dict:")
    print(f"   Type: {type(provider_from_dict)}")
    print(f"   Data: {provider_from_dict}")
    print(f"   model_dump(): {provider_from_dict.model_dump()}")
except Exception as e:
    print(f"\n5. ERROR creating ProviderConfig from dict: {e}")

# Check what happens if we parse without type info (just the base type)
print(f"\n6. Raw dict content:")
print(f"   Keys: {list(json_data.keys())}")
print(f"   'type' field: {json_data.get('type', 'MISSING')}")
print(f"   'model_id' field: {json_data.get('model_id', 'MISSING')}")
