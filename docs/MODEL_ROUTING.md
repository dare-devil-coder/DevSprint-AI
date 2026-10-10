<!-- Capability-based LLM model choices and verified fallback behavior. -->
# Model routing

DevSprint AI needs text generation that returns a JSON object. It filters each provider's catalog to generation models suitable for contract reasoning, Python coding, verification, or short explanations. Audio, image, embedding, moderation, and reward models are excluded. Catalog entries alone do not establish that a key can invoke a model, so the choices below were tested with live JSON requests on 11 October 2026. Model availability and quotas can change.

## Ordered routes

| Task | First | Second | Third | Fourth |
| --- | --- | --- | --- | --- |
| Requirements, Architecture, Verifier | Groq `openai/gpt-oss-120b` | Gemini `gemini-2.5-flash` | OpenRouter `qwen/qwen3-coder-flash` | NVIDIA `nvidia/nemotron-3-super-120b-a12b` |
| Coder, Test Writer, Self-Healing | OpenRouter `qwen/qwen3-coder-flash` | Groq `openai/gpt-oss-120b` | NVIDIA `nvidia/nemotron-3-super-120b-a12b` | Gemini `gemini-2.5-flash` |
| Project Details levels 1–2 | Groq `openai/gpt-oss-20b` | Gemini `gemini-2.5-flash` | NVIDIA `z-ai/glm-5.3-flash` | OpenRouter `qwen/qwen3-coder-flash` |
| Project Details levels 3–4 | Groq `openai/gpt-oss-120b` | Gemini `gemini-2.5-flash` | NVIDIA `nvidia/nemotron-3-super-120b-a12b` | OpenRouter `qwen/qwen3-coder-flash` |

The first coding choice specializes in code. The larger Groq and NVIDIA models are used for planning, repairs, and verification. Short learner explanations start with a smaller, faster Groq model. All selected choices returned valid JSON in the live probes. `OPENAI_API_KEY`, when configured, adds the legacy OpenAI model as another fallback; an explicit `OPENAI_MODEL_CHEAP` request keeps that OpenAI model first for level 1–2 explanations.

The router tries only providers with configured keys. It moves to the next choice on authentication failure, unsupported model, quota or rate error, timeout, empty output, or invalid JSON. It briefly cools down failed providers or models, then retries them later. It never logs keys or prompt contents. A model producing syntactically valid but semantically wrong project data can still fail the agent's own validation; that remains visible as an agent error.

## Live checks

| Provider | Catalog | JSON completion |
| --- | --- | --- |
| OpenRouter | HTTP 200 | Qwen3 Coder Flash: HTTP 200, valid JSON |
| Groq | HTTP 200 | GPT OSS 120B and 20B: HTTP 200, valid JSON |
| NVIDIA | HTTP 200 | Nemotron 3 Super and GLM 5.3 Flash: HTTP 200, valid JSON |
| Gemini | HTTP 200 | Gemini 2.5 Flash: HTTP 200, valid JSON |

With deliberately invalid primary credentials, live routing recovered through Gemini for requirements, NVIDIA Nemotron Super for coding, and NVIDIA GLM Flash for low-cost explanations. Gemini 2.5 Pro and Flash Lite appeared in the catalog but returned HTTP 404 for this key. NVIDIA Nemotron 3.5 Lightning returned reasoning text instead of a JSON object on the small probe. They are excluded from the route.

On 11 October 2026, a fresh small JSON request to each configured route model returned HTTP 200 and a valid JSON object: OpenRouter Qwen3 Coder Flash, Groq GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, and Gemini 2.5 Flash. Qwen3 Coder Flash remains the coding primary because it is the coding-specialized model and passed the current request. This confirms basic key, endpoint, model, and JSON-mode access at probe time. It does not guarantee that larger project-generation prompts will avoid transient latency or provider-specific request limits. The coding smoke check also returned both requested Python files as parseable source. An isolated SerpApi search through `backend/serpapi_client.py` returned three results after the pinned `serpapi` package was installed in the project `.venv`. These checks do not replace a complete live demo run.

Recheck with `python -m scripts.probe_models`, `python -m scripts.probe_models --live`, and `python -m scripts.probe_models --router`. `--fallback` deliberately sends small requests with invalid credentials to test failover; it restores the real credentials in the process before exiting. Live generation consumes provider quota.

Provider references: [OpenRouter model metadata](https://openrouter.ai/docs/api/api-reference/models/get-models), [Groq supported models](https://console.groq.com/docs/models), [Groq JSON output](https://console.groq.com/docs/structured-outputs), [NVIDIA chat API](https://docs.api.nvidia.com/nim/reference/llm-apis), [Gemini model metadata](https://ai.google.dev/api/models), and [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai).
