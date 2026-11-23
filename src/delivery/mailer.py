import html
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence
from zoneinfo import ZoneInfo

import aiosmtplib

from src.config import get_settings
from src.db.models import MarketBrief

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

SENTIMENT_COLORS = {
    "BULLISH": "#16a34a",
    "BEARISH": "#dc2626",
    "NEUTRAL": "#64748b",
}


class EmailDigestService:
    """Renders and dispatches HTML End-of-Day market briefs via async SMTP."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def _render_html(self, briefs: Sequence[MarketBrief], report_date: str) -> str:
        cards_html: list[str] = []

        for brief in briefs:
            ann = brief.announcement
            color = SENTIMENT_COLORS.get(brief.sentiment.upper(), "#64748b")
            company = html.escape(ann.company_name)
            headline = html.escape(brief.headline)
            summary = html.escape(brief.raw_summary)
            category = html.escape(ann.category)

            takeaways_li = "".join(
                f"<li style='margin-bottom:4px;'>{html.escape(point)}</li>"
                for point in brief.key_takeaways
            )

            metrics = {k: v for k, v in (brief.financial_metrics or {}).items() if v}
            metrics_html = ""
            if metrics:
                pills = " | ".join(
                    f"<strong>{html.escape(k.replace('_', ' ').title())}:</strong> {html.escape(str(v))}"
                    for k, v in metrics.items()
                )
                metrics_html = (
                    f"<p style='font-size:13px;color:#334155;background:#f8fafc;"
                    f"padding:8px 10px;border-radius:6px;margin:10px 0;'>{pills}</p>"
                )

            pdf_link = (
                f"<a href='{html.escape(ann.pdf_url)}' style='color:#2563eb;text-decoration:none;"
                f"font-size:13px;font-weight:600;'>View Official BSE PDF &rarr;</a>"
                if ann.pdf_url
                else ""
            )

            cards_html.append(
                f"""
                <div style="border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:16px;background:#ffffff;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <span style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">
                            {company} &bull; {category}
                        </span>
                        <span style="background:{color};color:#ffffff;font-size:11px;font-weight:700;
                                     padding:3px 8px;border-radius:999px;">
                            {html.escape(brief.sentiment)} &bull; Impact {brief.impact_score}/10
                        </span>
                    </div>
                    <h3 style="margin:6px 0 8px 0;color:#0f172a;font-size:16px;">{headline}</h3>
                    <p style="margin:0 0 10px 0;color:#334155;font-size:14px;line-height:1.5;">{summary}</p>
                    {metrics_html}
                    <ul style="margin:8px 0 12px 18px;padding:0;color:#1e293b;font-size:14px;line-height:1.5;">
                        {takeaways_li}
                    </ul>
                    {pdf_link}
                </div>
                """
            )

        return f"""
        <html>
          <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                       background:#f1f5f9;padding:24px;margin:0;">
            <div style="max-width:680px;margin:0 auto;">
              <h1 style="color:#0f172a;font-size:22px;margin-bottom:4px;">TradeAlign-AI Daily Market Brief</h1>
              <p style="color:#64748b;font-size:14px;margin-top:0;margin-bottom:20px;">
                BSE High-Impact Corporate Filings &bull; {report_date} (IST) &bull; {len(briefs)} filings
              </p>
              {"".join(cards_html)}
              <p style="color:#94a3b8;font-size:12px;text-align:center;margin-top:24px;">
                Generated autonomously by TradeAlign-AI. Not financial advice.
              </p>
            </div>
          </body>
        </html>
        """

    async def send_digest(self, briefs: Sequence[MarketBrief]) -> bool:
        """Send an HTML email containing all provided market briefs."""
        if not briefs:
            logger.info("No new high-impact briefs to email.")
            return False

        report_date = datetime.now(IST).strftime("%d %b %Y")
        message = MIMEMultipart("alternative")
        message["Subject"] = f"TradeAlign-AI BSE Brief ({report_date}) — {len(briefs)} High-Impact Filings"
        message["From"] = self._settings.smtp_user
        message["To"] = self._settings.recipient_email

        html_body = self._render_html(briefs, report_date)
        message.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            message,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            start_tls=True,
            username=self._settings.smtp_user,
            password=self._settings.smtp_password.get_secret_value(),
        )
        logger.info("Sent EOD digest with %d briefs to %s.", len(briefs), self._settings.recipient_email)
        return True