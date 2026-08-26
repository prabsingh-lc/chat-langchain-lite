"""Centralized model initialization.

Credentials and routing come from the **ambient environment**, not from
constructor arguments:

    ANTHROPIC_API_KEY      - key the gateway (or Anthropic) authenticates with
    ANTHROPIC_BASE_URL     - set to the LangSmith Gateway to route through it;
                             unset for a direct Anthropic connection

`langchain_anthropic` reads both automatically, so the constructor below stays
a plain `init_chat_model(...)` call. Nothing here reads a gateway credential
out of `.env` — set them in your shell (or, in CI, as Actions secrets) and the
same code works in both places.
"""

import os
from dotenv import load_dotenv

# override=False: the ambient environment wins; `.env` only fills in gaps.
# This is what lets the shell-provided gateway credentials take precedence
# over any stale values left in a local `.env`.
load_dotenv(override=False)

from langchain.chat_models import init_chat_model

# MODEL_CONFIG is the single source the frontend's Gateway pane reads. base_url
# is reported from the environment so the pane reflects however this process
# was actually configured, rather than a value hardcoded here.
MODEL_CONFIG = {
    "model": os.getenv("AGENT_MODEL", "claude-sonnet-4-6"),
    "provider": "anthropic",
    "base_url": os.getenv("ANTHROPIC_API_URL") or os.getenv("ANTHROPIC_BASE_URL") or "",
}

model = init_chat_model(
    model=MODEL_CONFIG["model"],
    model_provider=MODEL_CONFIG["provider"],
    max_tokens=300,  # Bug 4 (intentional): truncates complex technical answers
    temperature=0,
)

# --- Alternatives -------------------------------------------------------------
# Direct OpenAI:   model = init_chat_model("openai:gpt-4.1-mini")
# Direct Anthropic: unset ANTHROPIC_BASE_URL; the call above is unchanged.
#
# Azure OpenAI:
#   from langchain_openai import AzureChatOpenAI
#   model = AzureChatOpenAI(azure_deployment="gpt-4.1-mini", streaming=True)
#
# AWS Bedrock:
#   from langchain_aws import ChatBedrockConverse
#   model = ChatBedrockConverse(
#       provider="anthropic",
#       model_id="anthropic.claude-sonnet-4-20250514-v1:0",
#   )
