import logging
from typing import Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.ai.schemas import MarketBriefOutput
from src.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are a Senior Indian Equity Research Analyst specializing in BSE/NSE corporate filings.
Analyze the attached corporate filing PDF and produce a concise, factual market brief.

STRICT RULES:
1. Ground every number in the attached PDF. Never invent or estimate figures.
2. Preserve Indian financial units (₹ Crores, ₹ Lakhs, bps, YoY, QoQ) exactly as reported.
3. Score impact_score honestly: routine filings (trading window closure, investor meet intimations, loss of share certificates) MUST score 1-3. Major earnings, dividends, acquisitions, or large order wins score 7-10.
4. Keep key_takeaways crisp, scannable, and free of regulatory boilerplate.
"""


class GeminiAnalyzer:
    """Async multimodal PDF analyzer powered by the Google GenAI SDK."""

    def __init__(self, model: Optional[str] = None) -> None:
        settings = get_settings()
        self._model = model or settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    @retry(
        retry=retry_if_exception_type(genai_errors.APIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def analyze_filing(
        self,
        company_name: str,
        subject: str,
        category: str,
        pdf_bytes: bytes,
    ) -> MarketBriefOutput:
        """
        Send raw PDF bytes to Gemini and return a strictly validated MarketBriefOutput.
        """
        user_prompt = (
            f"Company: {company_name}\n"
            f"BSE Category: {category}\n"
            f"Filing Subject: {subject}\n\n"
            "Analyze the attached PDF filing and generate the structured market brief."
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
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
            raise ValueError(f"Gemini returned an empty response for {company_name} ({subject}).")

        return MarketBriefOutput.model_validate_json(response.text)