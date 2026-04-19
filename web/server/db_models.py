from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    email         = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)

class License(Base):
    __tablename__ = "licenses"
    id         = Column(Integer, primary_key=True)
    key        = Column(String, unique=True, nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan       = Column(String, nullable=False)
    hwid       = Column(String, nullable=True)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

class Plugin(Base):
    __tablename__ = "plugins"
    id          = Column(Integer, primary_key=True)
    name        = Column(String, nullable=False)
    description = Column(String, nullable=False)
    code        = Column(String, nullable=False)
    author_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    downloads   = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
