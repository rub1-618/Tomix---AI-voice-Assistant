from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_models import Base

# путь к файлу базы данных
DATABASE_URL = "sqlite:///./tomix.db"

# создай движок
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# создай фабрику сессий — SessionLocal
# подсказка: sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# функция которая создаёт все таблицы из models.py
def init_db():
    Base.metadata.create_all(engine)

# функция-генератор для FastAPI dependency injection
# открывает сессию, отдаёт её, закрывает после запроса
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
