import os

# ── Thresholds ────────────────────────────────────────────────────────────────
HIGH_VALUE_THRESHOLD = 10_000       # $10K+ → heightened approval scrutiny
PRICE_DEVIATION_PCT  = 0.10         # 10% tolerance on unit price vs. contract
MAX_RETRY_ATTEMPTS   = 2            # max ingestion self-correction retries
CONFIDENCE_THRESHOLD = 0.70         # re-extract if below this

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "invoice_processor.db")


def get_llm(temperature: float = 0):
    """
    Return a LangChain chat model based on available API keys.
    Priority: OpenAI → Grok (xAI) → Anthropic Claude
    """
    if api_key := os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o",
            api_key=api_key,
            temperature=temperature,
        )

    if api_key := os.getenv("XAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="grok-beta",
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            temperature=temperature,
        )

    if api_key := os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-opus-4-5",
            api_key=api_key,
            temperature=temperature,
        )

    raise ValueError(
        "No LLM API key found. Set OPENAI_API_KEY, XAI_API_KEY, or ANTHROPIC_API_KEY in .env"
    )
