# temporal-strands-plugin

A production-grade integration between **Strands Agents** and **Temporal (Python)**.

- All model inference and tool execution happen in **Temporal Activities** for reliability and retries.
- **Workflows** orchestrate the Strands event loop deterministically.
- Uses Temporal's **Pydantic data converter** to serialize data safely across clients/workers.
- Includes a **Bedrock provider** (streaming via `converse_stream`) and a **deterministic Echo provider** for testing.
- Ships with a minimal **agent workflow**, hooks to intercept tools, activities, and tests.
