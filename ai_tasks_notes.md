# Conductor AI Tasks — v3.30.0.rc3

## Prerequisites

1. Enable AI integration in server config:
   ```
   conductor.integrations.ai.enabled=true
   ```
2. Register an LLM provider integration via the UI (Integrations menu) or API.

## Available AI Task Types

| Task type              | Purpose                        |
|------------------------|--------------------------------|
| LLM_TEXT_COMPLETE      | Single prompt → completion     |
| LLM_CHAT_COMPLETE      | Multi-turn chat, tool use      |
| LLM_INDEX_TEXT         | Index text into a vector DB    |
| LLM_SEARCH_INDEX       | Search a vector DB             |
| LLM_GENERATE_EMBEDDINGS| Generate embeddings            |
| LLM_STORE_EMBEDDINGS   | Store embeddings               |
| LLM_GET_EMBEDDINGS     | Retrieve embeddings            |

## Common Input Parameters (all LLM tasks)

- `llmProvider` — name of your registered integration (required)
- `model` — model identifier, e.g. `gpt-4o`, `claude-sonnet-4-6` (required)
- `temperature`, `topP`, `maxTokens`, `stopWords`
- `promptVariables` — Map<String, Object> for template variable substitution

## LLM_TEXT_COMPLETE Extras

- `promptName` — name of a saved prompt template
- `prompt` — raw prompt string (also set `allowRawPrompts: true`)
- `jsonOutput` — true to get JSON back

## LLM_CHAT_COMPLETE Extras

- `instructions` — system prompt
- `userInput` — user message (shorthand for single-turn)
- `messages` — explicit message list for multi-turn history
- `tools` — Conductor workers/tasks the model can call as tools
- `jsonOutput` + `outputSchema` — for structured JSON output
- `thinkingTokenLimit` — for Anthropic thinking models
- `reasoningEffort` — for OpenAI reasoning models (low/medium/high)

## Example Files

- `text_complete_workflow.json` — LLM_TEXT_COMPLETE workflow
- `chat_complete_workflow.json` — LLM_CHAT_COMPLETE workflow
