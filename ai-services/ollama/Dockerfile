# Shared Ollama runtime for the Release 2 cloud bonus (B1-B4: enabling
# AI-Mode/MCP/RAG/Multi-Agent in the cloud). Not used by the required
# baseline cloud deployment, where these services stay disabled, and not
# used locally (Ollama runs as a host process there, per the Release 0/1
# briefs). This image only exists so the bonus AI services have something
# to call in Azure, where there is no "host machine" to reach.
#
# The small qwen2.5:0.5b model (already the default model used by AI-Mode,
# the Multi-Agent Server, and the agentic loop) is pulled at build time, so
# the Container App can start serving immediately instead of downloading
# ~400MB on its first request.
FROM ollama/ollama:latest

# Bake the model in. OLLAMA_HOST is left unset here so the server binds (and
# the `ollama` client connects) on the default loopback address during the
# build; it is only switched to 0.0.0.0 afterwards, for the runtime CMD.
RUN (ollama serve &) \
    && sleep 5 \
    && for i in $(seq 1 10); do ollama pull qwen2.5:0.5b && break || sleep 3; done

# At runtime, bind on all interfaces so other Container Apps in the same
# Container Apps Environment can reach this one over the internal network
# (matching the internal-only ingress used for the other backing services).
ENV OLLAMA_HOST=0.0.0.0:11434
EXPOSE 11434
