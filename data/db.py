# data/db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# Central path handling
from .paths import DB_PATH   # ⬅ only need DB_PATH now

# -----------------------------------------
# Build absolute SQLite URI using DB_PATH
# -----------------------------------------
# Example: sqlite:///C:/Users/.../RegisTree/registree.db
engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    future=True,
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)

def init_db():
    """Create tables if they don't already exist."""
    # Ensure the directory containing registree.db exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
