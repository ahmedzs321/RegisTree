from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# SQLite DB file lives next to app.py (RegisTree folder)
engine = create_engine("sqlite:///registree.db", future=True)

# Use one SessionLocal() per window/controller
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
    )

def init_db():
    # Creates tables for all models registered on Base (none yet on Day 1)
    Base.metadata.create_all(engine)
