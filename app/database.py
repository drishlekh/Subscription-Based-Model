# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set.")

# Create a SQLAlchemy engine
# pool_pre_ping=True: checks connections for liveness before handing them out from the pool.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,  # Default is 5
    max_overflow=20 # Default is 10
)

# Each instance of the SessionLocal class will be a database session.
# autocommit=False: You need to explicitly commit changes.
# autoflush=False: You need to explicitly flush changes (send them to DB before commit).
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy models to inherit from.
Base = declarative_base()

# Dependency to get a DB session
def get_db():
    """
    Why this function is necessary:
    - Manages the lifecycle of a database session for each request.
    - Ensures that the database session is always closed after the request is finished,
      even if an error occurs. This prevents resource leaks.
    What it's doing:
    - Creates a database session (db = SessionLocal()).
    - Yields the session to the path operation function.
    - After the path operation function finishes (or an exception occurs),
      it closes the session (db.close()).
    How it's used:
    - Injected into path operation functions using FastAPI's dependency injection system:
      `db: Session = Depends(get_db)`
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()