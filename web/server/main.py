from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, init_db
from security import hash_password, generate_key, verify_password
from db_models import User, License, Plugin


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class PluginRequest(BaseModel):
    name: str
    description: str
    code: str
    author_id: int

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/validate")
def validate(key: str, hwid: str, db: Session = Depends(get_db)):
    license = db.query(License).filter(License.key == key).first()
    if not license:
        raise HTTPException(404, "Key not found")
    if not license.is_active:
        raise HTTPException(403, "Key deactivated")
    if not license.hwid:
        license.hwid = hwid
        db.commit()
    elif license.hwid != hwid:
        raise HTTPException(403, "Key is attached to the machine")

@app.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    # проверяем что email не занят
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email is already registered")
    
    hashed = hash_password(data.password)

    user = User(email=data.email, password_hash=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)  # чтобы получить user.id

    key = generate_key()
    license = License(key=key, user_id=user.id, plan="free")
    db.add(license)
    db.commit()
    return {"email": user.email, "key": key, "plan": "free"}

@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Email not found")
    
    if not verify_password(data.password, existing.password_hash):
        raise HTTPException(status_code=401, detail="Password is not verified")
    
    license = db.query(License).filter(License.user_id == existing.id).first()
    return {"email": existing.email, "plan": license.plan, "key": license.key}

@app.get("/plugins")
def plugins(db: Session = Depends(get_db)):
    existing = db.query(Plugin).filter(Plugin.is_verified == True).all()
    return [{"name": p.name, "description": p.description, "downloads": p.downloads} for p in existing]

@app.post("/plugins")
def plugins(data: PluginRequest, db: Session = Depends(get_db)):

    plugin = Plugin(name = data.name, description = data.description, code = data.code, author_id = data.author_id, is_verified=False)
    db.add(plugin)
    db.commit()
    db.refresh(plugin)
    return {"name": plugin.name, "description": plugin.description, "code": plugin.code, "author_id": plugin.author_id, "status": "pending"}