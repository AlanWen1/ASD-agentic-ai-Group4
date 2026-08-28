import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://bills_user:bills_password@localhost:6004/bills"
)

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:0.5b"
)
