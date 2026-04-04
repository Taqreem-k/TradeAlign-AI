import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings
import logging

logger = logging.getLogger(__name__)

def send_premarket_brief(html_content: str):
    if not settings.SENDER_EMAIL or not settings.Email_APP_PASSWORD:
        logger.error("Email credentials are missing in the .env file!")
        return
    
    logger.info("Connecting to SMTP server...")

    msg= MIMEMultipart()
    msg['From'] = settings.SENDER_EMAIL
    msg['To'] = settings.RECEIVER_EMAIL
    msg['Subject'] = "Your Pre-Market Alpha Brief"

    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com',587)
        server.starttls()
        server.login(settings.SENDER_EMAIL, settings.Email_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info("Pre-market brief emailed successfully!")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")