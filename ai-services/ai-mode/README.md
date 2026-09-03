# AI-Mode

Release 0 requirement: a shared AI-mode capability (Ollama runtime + one or
more approved open-source LLMs — Qwen, Llama, or DeepSeek) that every
microservice's backend uses.

Not centralised here yet. Right now each backend talks to the shared Ollama
runtime directly over HTTP (`OLLAMA_URL`, default
`http://host.docker.internal:11434`, model `qwen2.5:0.5b` in most services).
If the team wants to satisfy this folder's intent literally, the shared
Ollama-calling logic (building the prompt, calling `/api/generate` or
`/api/chat`, handling errors/timeouts) could be extracted into a small
shared module or its own service that the five backends import/call instead
of each re-implementing it.
