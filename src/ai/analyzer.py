import logging
from typing import Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.ai.schemas import MarketBriefOutput
from src.config import get_settings

logger = logging.getLogger(__name__)

FALLBACK_MODELS = [
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

SYSTEM_INSTRUCTION = """You are a Senior Indian Equity Research Analyst specializing in NSE/BSE corporate filings.
Analyze the attached corporate filing PDF and produce a concise, factual market brief.

STRICT RULES:
1. Ground every number in the attached PDF. Never invent or estimate figures.
2. Preserve Indian financial units (₹ Crores, ₹ Lakhs, bps, YoY, QoQ) exactly as reported.
3. Score impact_score honestly: routine filings (trading window closure, investor meet intimations, loss of share certificates) MUST score 1-3. Major earnings, dividends, acquisitions, or large order wins score 7-10.
4. Keep key_takeaways crisp, scannable, and free of regulatory boilerplate.
"""


class GeminiAnalyzer:
    """Async multimodal PDF analyzer with automatic multi-model failover."""

    def __init__(self, model: Optional[str] = None) -> None:
        settings = get_settings()
        primary = model or settings.gemini_model
        # Deduplicated chain: configured model first, then Free Tier fallbacks
        self._models = list(dict.fromkeys([primary, *FALLBACK_MODELS]))
        self._client = genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(),
            http_options=types.HttpOptions(api_version="v1beta"),
        )

    async def analyze_filing(
        self,
        symbol: str,
        company_name: str,
        subject: str,
        category: str,
        pdf_bytes: bytes,
    ) -> MarketBriefOutput:
        """
        Send raw PDF bytes to Gemini and return a strictly validated MarketBriefOutput.
        Automatically fails over to the next model on 404 (retired), 429 (quota), or 503 (busy).
        """
        user_prompt = (
            f"NSE Symbol: {symbol}\n"
            f"Company: {company_name}\n"
            f"NSE Category: {category}\n"
            f"Filing Subject: {subject}\n\n"
            "Analyze the attached PDF filing and generate the structured market brief."
        )

        last_exc: Optional[Exception] = None
        for model_name in self._models:
            try:
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                        user_prompt,
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_schema=MarketBriefOutput,
                        temperature=0.1,
                    ),
                )

                if not response.text:
                    raise ValueError(f"Gemini ({model_name}) returned an empty response for {symbol}.")

                return MarketBriefOutput.model_validate_json(response.text)

            except genai_errors.APIError as exc:
                last_exc = exc
                if exc.code in (404, 429, 500, 502, 503, 504):
                    logger.warning(
                        "Model %s unavailable (HTTP %s) for [%s]; trying next fallback model.",
                        model_name,
                        exc.code,
                        symbol,
                    )
                    continue
                raise

        assert last_exc is not None
        raise last_exc