import os
import secrets
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from database import db, create_document, get_documents

app = FastAPI(title="Travel Planner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# Utility functions
# ----------------------

def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _get_user_by_email(email: str) -> Optional[dict]:
    return db["user"].find_one({"email": email}) if db else None


def _get_user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    return db["user"].find_one({"tokens": token}) if db else None


# ----------------------
# Models
# ----------------------

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    name: str
    email: EmailStr


class TripCreateRequest(BaseModel):
    prompt: str = Field(..., description="Natural language description of the desired trip")
    days: int = Field(3, ge=1, le=30)
    destination: Optional[str] = None
    budget: Optional[str] = Field(None, description="shoestring | standard | luxury")
    title: Optional[str] = None


# ----------------------
# Routes
# ----------------------

@app.get("/")
def root():
    return {"message": "Travel Planner Backend is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()[:10]
        else:
            response["database"] = "❌ Not Available"
    except Exception as e:
        response["database"] = f"⚠️ Error: {str(e)[:80]}"
    return response


# ---- Auth ----

@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    existing = _get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    salt = secrets.token_hex(16)
    password_hash = _hash_password(req.password, salt)
    token = secrets.token_hex(24)

    user_doc = {
        "name": req.name,
        "email": str(req.email),
        "password_hash": password_hash,
        "salt": salt,
        "tokens": [token],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    db["user"].insert_one(user_doc)
    return AuthResponse(token=token, name=req.name, email=req.email)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    user = _get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    expected = _hash_password(req.password, user.get("salt", ""))
    if expected != user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_hex(24)
    db["user"].update_one({"_id": user["_id"]}, {"$push": {"tokens": token}, "$set": {"updated_at": datetime.now(timezone.utc)}})
    return AuthResponse(token=token, name=user.get("name", ""), email=user.get("email", ""))


@app.get("/api/me")
def me(authorization: Optional[str] = Header(default=None)):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    token = (authorization or "").replace("Bearer ", "").strip()
    user = _get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"name": user.get("name"), "email": user.get("email")}


# ---- Trips ----


def _generate_itinerary(prompt: str, days: int, destination: Optional[str], budget: Optional[str]) -> List[Dict[str, Any]]:
    budget_hint = {
        "shoestring": ["street food", "free walking tours", "public transit"],
        "standard": ["local bistros", "top sights", "rideshare"],
        "luxury": ["fine dining", "private tours", "chauffeur"],
    }
    hints = budget_hint.get((budget or "standard").lower(), budget_hint["standard"])
    itinerary = []
    for d in range(1, days + 1):
        day_plan = {
            "day": d,
            "theme": f"Day {d} • {destination or 'Explorer'}",
            "morning": f"Start with {hints[0]} near the main square. Stroll through a scenic district inspired by: {prompt[:80]}",
            "afternoon": f"Visit two must‑see spots. Consider a museum or viewpoint. Use {hints[1]}.",
            "evening": f"Dinner with a view, then a relaxing walk. End with {hints[2]} back to stay.",
        }
        itinerary.append(day_plan)
    return itinerary


@app.post("/api/trips")
def create_trip(req: TripCreateRequest, authorization: Optional[str] = Header(default=None)):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    token = (authorization or "").replace("Bearer ", "").strip()
    user = _get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    itinerary = _generate_itinerary(req.prompt, req.days, req.destination, req.budget)
    title = req.title or (req.destination or "Custom Trip") + f" • {req.days} days"

    trip_doc = {
        "user_id": str(user["_id"]),
        "title": title,
        "prompt": req.prompt,
        "days": req.days,
        "itinerary": itinerary,
        "destination": req.destination,
        "budget": req.budget,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    inserted_id = db["trip"].insert_one(trip_doc).inserted_id
    trip_doc["_id"] = str(inserted_id)
    return trip_doc


@app.get("/api/trips")
def list_trips(authorization: Optional[str] = Header(default=None)):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    token = (authorization or "").replace("Bearer ", "").strip()
    user = _get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    trips = list(db["trip"].find({"user_id": str(user["_id"]) }).sort("created_at", -1))
    # Convert ObjectId to string
    for t in trips:
        t["_id"] = str(t["_id"])
    return trips


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
