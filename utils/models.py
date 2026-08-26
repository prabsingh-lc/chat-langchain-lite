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
load_dotenv(override=False)

from langchain.chat_models import init_chat_model

GATEWAY_URL = "https://gateway.smith.langchain.com/anthropic"

# Routing and credential are chosen together, because they are not independent:
# the gateway authenticates with a LANGSMITH key, direct Anthropic with an
# ANTHROPIC key. Pairing a gateway URL with an Anthropic key (or the reverse)
# yields a 401 that reads like a bad provider key, or a bare
# "Could not resolve authentication method" when no key resolves at all.
#
# Set AGENT_ROUTE to pick:
#   gateway (default) -> LangSmith Gateway, authenticated with LANGSMITH_API_KEY
#   direct            -> Anthropic directly, authenticated with ANTHROPIC_API_KEY
#
# Gateway is the default deliberately: a shell that exports ANTHROPIC_BASE_URL
# for some other project would otherwise silently redirect this agent at an
# endpoint its key is not valid for.
_route = (os.getenv("AGENT_ROUTE") or "gateway").strip().lower()

if _route == "direct":
    _base = os.getenv("ANTHROPIC_API_URL") or os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
    try:
        _key = os.environ["ANTHROPIC_API_KEY"]
    except KeyError:
        raise RuntimeError(
            "AGENT_ROUTE=direct requires ANTHROPIC_API_KEY. "
            "Unset AGENT_ROUTE to use the LangSmith Gateway instead."
        ) from None
else:
    _base = GATEWAY_URL
    try:
        _key = os.environ["LANGSMITH_API_KEY"]
    except KeyError:
        raise RuntimeError(
            "The default gateway route requires LANGSMITH_API_KEY (set it in .env). "
            "For a direct Anthropic connection set AGENT_ROUTE=direct."
        ) from None

# Model id is resolved per call, not frozen at import. setup.py seeds one
# baseline experiment per model by setting CHAT_LANGCHAIN_LITE_MODEL inside a
# loop in a single process — a module-level singleton silently ignores that,
# which produced "haiku vs sonnet" experiments that were really the same model
# twice (identical latency and cost, differing only in trace metadata).
DEFAULT_MODEL = "claude-sonnet-4-6"


def resolve_model_id() -> str:
    """The model id for the next call, honouring both override env vars."""
    return (
        os.getenv("CHAT_LANGCHAIN_LITE_MODEL")
        or os.getenv("AGENT_MODEL")
        or DEFAULT_MODEL
    )


def get_model(model_id: str | None = None):
    """Build a chat model on the active route. Call per agent build."""
    return init_chat_model(
        model=model_id or resolve_model_id(),
        model_provider="anthropic",
        base_url=_base or None,
        api_key=_key,
        max_tokens=300,  # Bug 4 (intentional): truncates complex answers
        temperature=0,
    )


# MODEL_CONFIG is the single source the frontend's Gateway pane reads.
MODEL_CONFIG = {
    "model": resolve_model_id(),
    "provider": "anthropic",
    "base_url": _base,
}

# Back-compat singleton for callers that just want "the" model.
model = get_model()


def anthropic_client_kwargs() -> dict:
    """Connection kwargs for a raw `anthropic.Anthropic()` client.

    Evaluator judges build their own client rather than going through the
    LangChain wrapper above. Routing them here keeps every model call in the
    process on one route, so CI needs only the credential that route uses.
    """
    return {"base_url": _base or None, "api_key": _key}


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
