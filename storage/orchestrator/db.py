from sqlmodel import create_engine

DATABASE_URL = "sqlite:///./storage.db"
engine = create_engine(DATABASE_URL, echo=True)