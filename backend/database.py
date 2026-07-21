from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# We use SQLite for the hackathon (zero setup, writes to a local file).
# This is easily upgradeable to PostgreSQL later by just changing this URL.
SQLALCHEMY_DATABASE_URL = "sqlite:///./sentinel.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get DB session in our FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()