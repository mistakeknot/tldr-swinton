# Harness and Model Capabilities

Last verified: 2026-07-21

This is the capability baseline behind tldr-swinton's adaptive integration. It is intentionally dated because agent harnesses and frontier models change quickly.

## What changed

### Context capacity increased

- OpenAI's current GPT-5.6 family exposes roughly one-million-token context windows and improved token efficiency for complex coding and agent workflows. Its current guidance also adds programmatic tool calling, persisted reasoning, and multi-agent orchestration.
- Anthropic's current Claude Fable 5, Opus 4.8, and Sonnet 5 models expose one-million-token context windows; Haiku 4.5 remains smaller.

Large context is capacity, not relevance selection. It reduces the risk of an immediate hard limit, but irrelevant search output still costs tokens, time, and attention. tldrs therefore optimizes what enters a context rather than assuming every file must be compressed first.

### Harnesses isolate exploration

- Claude Code's Explore and Plan subagents run with independent context windows. Skills can set `context: fork` and select `agent: Explore`, returning only a summary to the main conversation.
- Codex provides built-in explorer subagents, parallel agent threads, tool-output caps, and automatic compaction. Its guidance recommends offloading noisy exploration and test logs while keeping requirements and decisions in the main thread.

This makes an unconditional session-start dump or a second structural dump after every large Read counterproductive. tldr-swinton now uses forked reconnaissance in Claude Code, adaptive guidance in Codex, and explicit `distill` packets for workers that need a bounded handoff.

### Tool orchestration improved

- Current OpenAI model guidance recommends lean tool sets and programmatic tool calling for bounded, tool-heavy stages.
- Claude Code skills load descriptions eagerly and full skill content on invocation; invoked content remains in context. Concise, specific triggers matter.
- MCP remains the portable live-tool boundary, while Agent Skills provide portable task guidance with optional harness-specific extensions.

The plugin keeps CLI/MCP commands precise and moves routing policy into short skills. It does not add another always-on enforcement layer.

## Stable routing policy

| Situation | Preferred route |
|-----------|-----------------|
| Known small edit | Read/edit directly |
| Unfamiliar or large area | `structure`, `arch`, or semantic `find` in an explorer context |
| Non-trivial diff | `diff-context --preset compact` |
| Cross-file risk | `context`, `impact`, or `change-impact` |
| Parallel worker | Explorer thread or `distill --budget ...` handoff |
| Repeated prompt prefix | `cache-friendly` only when cache reuse is measured |

Do not route by model name in durable skills. Route by observable task shape and available harness isolation. Re-run representative evaluations when model, harness, tool schema, prompt caching, or pricing changes.

## Evaluation contract

Measure more than input-token reduction:

- task success and final-answer completeness
- required evidence and file/symbol precision
- total input/output/cached tokens
- latency and tool-call count
- duplicate or irrelevant context
- correctness after compaction or delegation

A shorter context is an improvement only when the completed task still meets its quality bar.

## Primary sources

- [OpenAI Codex manual](https://developers.openai.com/codex/codex-manual.md)
- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI model catalog](https://developers.openai.com/api/docs/models)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [Claude models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Agent Skills standard](https://agentskills.io)
- [Model Context Protocol](https://modelcontextprotocol.io)
