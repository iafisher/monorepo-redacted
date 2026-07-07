`lib/llm` is a library for interacting with large language models.

```python
model = "haiku"
app_name = "myapp::myfeature"

# Multi-message conversation
conversation = Conversation.start(db, model=model, app_name=app_name, system_prompt="...")
print(conversation.conversation_id)
response = conversation.prompt(db, "What is the capital of Ecuador?")

# One-shot response
response = llm.oneshot(db, "What is the capital of Ecuador?", model=model, app_name=app_name, system_prompt="...")
```

## Model support
`lib/llm` supports models from OpenAI (GPT), Anthropic (Claude), and Google (Gemini), with experimental support for Inception Labs's [Mercury 2](https://docs.inceptionlabs.ai/get-started/models) model.

## Storage
LLM conversations are stored in the `llm_v3_conversations` table in Postgres. The raw JSON of the conversation is stored as a blob.
