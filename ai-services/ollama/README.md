# Shared Ollama runtime (cloud bonus only)

This folder exists only to containerise Ollama for the Release 2 cloud
bonus marks (B1 Cloud AI-Mode, and B2/B3/B4 if those are attempted too).
It is **not** part of the required baseline:

- Locally, Ollama is a host process per the Release 0/1 briefs; nothing
  here is used for local deployment.
- In the required cloud deployment, AI-Mode, MCP, RAG and the Multi-Agent
  Server stay disabled by default, so this Ollama container is not needed
  there either.

It is deployed only when demonstrating a cloud bonus item, so that
AI-Mode (and, if enabled, the other AI services) have a real Ollama
runtime to call from inside Azure, where there is no host machine to
reach via `host.docker.internal`.

The image bakes in `qwen2.5:0.5b` — the same default model already used
by AI-Mode, the Multi-Agent Server and the agentic loop — at build time,
so the container is ready to serve as soon as it starts.

Deployed as an internal-only Container App (`ollama`, port 11434) with
extra CPU/memory (1.0 vCPU / 2Gi) compared with the other backing
services, since LLM inference is heavier than a typical REST call.
