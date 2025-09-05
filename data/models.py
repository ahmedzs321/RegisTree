# For Day 1, we only define the SQLAlchemy Base.
# We'll add Student/Class/Attendance models later.

from sqlalchemy.orm import declarative_base

Base = declarative_base()
