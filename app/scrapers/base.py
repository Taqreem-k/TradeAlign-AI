from sqlalchemy.orm import Session
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaseScraper:
    def __init__(self, db: Session):
        self.db = db
        self.logger = logger

    def run(self):
        raise NotImplementedError("Subclasses must implement the run() method.")