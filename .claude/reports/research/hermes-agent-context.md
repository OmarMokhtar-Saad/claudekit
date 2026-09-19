# Hermes Agent Context Requirements & Native Model Limits

**Date**: 2026-09-15  
**Topic**: Hermes Agent minimum context, local/Ollama configuration, Hermes 3 8B/4 native contexts

## Hermes Agent Framework Requirements

**Minimum context**: 64,000 tokens (hard requirement; models below this are rejected at startup).  
**Source**: [NousResearch/hermes-agent issues](https://github.com/NousResearch/hermes-agent/issues/24140)

The 64K minimum is required to maintain sufficient working memory for multi-step tool-calling workflows and agent reasoning. Hermes Agent auto-detects context length from the model provider endpoint.

## Local Model & Ollama Configuration

**Critical limitation**: Ollama does NOT use a model's full native context window by default; it ranges from 4K–256K depending on VRAM.

**Configuration methods** (in priority order):
1. **Environment variable** (recommended): `OLLAMA_CONTEXT_LENGTH=64000 ollama serve`
2. **Systemd service override**: Edit systemd unit, add `Environment="OLLAMA_CONTEXT_LENGTH=64000"`, restart.
3. **Modelfile**: Bake context length into the model itself (persistent).

**Cannot override via OpenAI-compatible API endpoint** — context must be set server-side.  
**Verification**: Check `ollama ps` and inspect the CONTEXT column.

**Source**: [Hermes Agent integrations/providers docs](https://hermes-agent.nousresearch.com/docs/integrations/providers)

## Hermes 3 8B Native Context

**Base model**: Llama 3.1 8B  
**Native max context**: 128,000 tokens

Hermes 3 inherits Llama 3.1's 128K context window and Grouped-Query Attention (GQA) for efficient long-context handling. Practical usability depends on GPU memory for KV cache.

**Sources**:
- [Llama 3.1 blog (128K context)](https://huggingface.co/blog/llama31)
- [Hermes-3-Llama-3.1-8B model card](https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B)

## Hermes 4 14B Native Context

**Base model**: Qwen 3 14B  
**Native max context**: 32,768 tokens  
**Extended (YaRN scaling)**: 131,072 tokens

Hermes 4 uses Qwen 3 14B as its base, which supports flexible thinking/non-thinking modes and YaRN context extension for long sequences beyond 32K.

**Sources**:
- [Qwen/Qwen3-14B model card](https://huggingface.co/Qwen/Qwen3-14B)
- [NousResearch/Hermes-4-14B model card](https://huggingface.co/NousResearch/Hermes-4-14B)

## System Prompt & Tool Schema Token Size Guidance

**Not explicitly documented** in Hermes Agent official sources. Hermes Agent abstracts context management; the framework handles system prompt and tool schema overhead internally. For local Ollama deployments, allocate headroom: set `num_ctx` (Ollama's raw context parameter) ~10–15% above the 64K minimum (e.g., 73–74K) to account for framework overhead.

**Verification**: No official documentation found; this is an inference from common agent patterns.

## Summary Table

| Parameter | Hermes Agent Framework | Hermes 3 8B (Llama 3.1) | Hermes 4 14B (Qwen 3) |
|-----------|------------------------|------------------------|-----------------------|
| Minimum context | 64K tokens | 128K native | 32K native |
| Recommended | 64K+ (auto-detected) | Full 128K for agent use | 32K native, extend to 131K if needed |
| Ollama config | `OLLAMA_CONTEXT_LENGTH=64000` | Set per-model in Modelfile | Set per-model in Modelfile |
| Token estimation | Framework auto-estimates | GQA-based efficiency | YaRN extension available |

## Open Questions

1. **Exact system prompt + tool schema overhead**: Hermes Agent source (`model_metadata.py`) defines 64K minimum but does not break down how much is reserved for framework vs. user context. For precise tuning, inspect the running agent's prompt construction in `.claude/operations/` or Hermes Agent source.

2. **Ollama `num_ctx` vs. `OLLAMA_CONTEXT_LENGTH`**: Hermes Agent documentation does not differentiate these; both control context length, but behavior differs by Ollama version. Verify with `ollama ps`.
