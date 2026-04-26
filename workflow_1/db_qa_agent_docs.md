# DB Q&A Agent Workflow

## Overview

`db_qa_agent` is an agentic Conductor workflow that answers a user's natural-language question by dynamically querying a database through an MCP (Model Context Protocol) server. The LLM decides when—and how many times—to call the database tool before composing the final answer.

## How It Works

```
User question
     │
     ▼
┌─────────────────────────────────────────────┐
│  DO_WHILE (agentic_loop_ref, max 5 rounds)  │
│                                             │
│   ┌──────────────────────────────────────┐  │
│   │       LLM_CHAT_COMPLETE (chat_ref)   │  │
│   │  tools: [query_database]             │  │
│   └──────────────────────────────────────┘  │
│             │                               │
│             ▼ (if LLM calls a tool)         │
│   ┌──────────────────────────────────────┐  │
│   │  CALL_MCP_TOOL (dynamic subtask)     │  │
│   │  → MCP server → database             │  │
│   └──────────────────────────────────────┘  │
│             │                               │
│             └── history fed back next iter  │
│                                             │
│  Loop exits when: toolCalls == empty        │
│                OR iteration >= 5            │
└─────────────────────────────────────────────┘
     │
     ▼
Final answer (chat_ref.output.result)
```

### Execution flow

1. **Iteration 1** — `LLM_CHAT_COMPLETE` receives the question and the `query_database` tool spec.
   - If the LLM has enough context → returns the answer directly (no tool calls → loop exits).
   - If the LLM needs data → returns `toolCalls` listing which DB queries to run.

2. **Tool dispatch** — Conductor dynamically creates a `CALL_MCP_TOOL` subtask for each tool call the LLM returned. Each subtask contacts the MCP server and receives the DB results.

3. **Next iteration** — `LLM_CHAT_COMPLETE` runs again. The `getHistory()` mechanism inside the mapper automatically injects completed tool subtasks as `tool` messages in the conversation. The LLM sees the DB results and either calls more tools or produces the final answer.

4. **Loop exits** — when the LLM returns no `toolCalls` (answer is ready) or the iteration cap (5) is reached.

## Workflow Inputs

| Field | Type | Description |
|---|---|---|
| `question` | string | The user's natural-language question |
| `llmProvider` | string | Name of the registered LLM integration (e.g. `openai`, `azure_openai`) |
| `model` | string | Model identifier (e.g. `gpt-4o`, `claude-sonnet-4-6`) |
| `mcpServer` | string | MCP server URL, e.g. `http://localhost:3000/sse` |
| `mcpHeaders` | object | Optional auth headers for the MCP server, e.g. `{"Authorization": "Bearer <token>"}` |

## Workflow Outputs

| Field | Description |
|---|---|
| `answer` | The LLM's final answer to the question |
| `toolCallCount` | Number of agentic loop iterations that ran |

## Key Components

### `LLM_CHAT_COMPLETE` task

- **`instructions`** — System prompt. Instructs the LLM to use the DB tool when needed and stop when it has enough information.
- **`userInput`** — Passed directly from `workflow.input.question`.
- **`temperature: 0`** — Deterministic output for Q&A accuracy.
- **`tools`** — Declares the `query_database` tool:
  - `name: "query_database"` — The name the LLM must use in its tool call.
  - `type: "CALL_MCP_TOOL"` — Conductor task type to execute.
  - `configParams.mcpServer` — Static MCP server URL (not sent to LLM, used only for execution).
  - `inputSchema` — JSON Schema shown to the LLM so it knows what arguments to produce.

### `CALL_MCP_TOOL` task (dynamic)

Created automatically by Conductor when the LLM outputs tool calls. Not declared statically in the workflow.

Key fields populated at runtime:
- `mcpServer` — from `ToolSpec.configParams`
- `method` — tool name the LLM selected (e.g. the specific DB procedure)
- `arguments` — the LLM-generated query arguments

### `DO_WHILE` loop

Loop condition:
```javascript
if ($.agentic_loop_ref['iteration'] < 5
    && $.chat_ref['output']['toolCalls'] != null
    && $.chat_ref['output']['toolCalls'].length > 0) { true; } else { false; }
```
Stops when either the LLM stops calling tools or 5 iterations are exhausted (safety cap).

## Prerequisites

1. `conductor.integrations.ai.enabled=true` in server config.
2. LLM provider registered under the name used in `llmProvider` input.
3. An MCP server exposing a database (e.g. a PostgreSQL or SQLite MCP server) running and reachable at `mcpServer`.

## Example Input

```json
{
  "question": "How many orders were placed in March 2026?",
  "llmProvider": "openai",
  "model": "gpt-4o",
  "mcpServer": "http://localhost:3000/sse",
  "mcpHeaders": {}
}
```

## Example Output

```json
{
  "answer": "There were 1,482 orders placed in March 2026.",
  "toolCallCount": 2
}
```

## Extending the Workflow

**Add more tools** — Append to the `tools` array in `LLM_CHAT_COMPLETE`. Each entry must have `name`, `type`, `description`, and `inputSchema`. The LLM picks the right one based on the descriptions.

**Increase iteration cap** — Change `< 5` in the loop condition.

**Structured JSON output** — Set `"jsonOutput": true` and add `"outputSchema"` to the `LLM_CHAT_COMPLETE` task.

**Multiple MCP servers** — Add a second tool with a different `configParams.mcpServer` pointing to another database.
