import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from app.database.connection import engine, Base

from app.database import models

def create_tables():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

if __name__ == "__main__":
    create_tables()