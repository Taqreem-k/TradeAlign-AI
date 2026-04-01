import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:supersecretpassword@localhost:5432/alpharadar")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

settings = Settings()