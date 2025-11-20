"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    salt: str = Field(..., description="Per-user salt")
    tokens: List[str] = Field(default_factory=list, description="Active auth tokens")

class Trip(BaseModel):
    """
    Trips created by users via prompt. Collection name: "trip"
    """
    user_id: str = Field(..., description="ID of the user owner as string")
    title: str = Field(..., description="Trip title")
    prompt: str = Field(..., description="Original prompt used to generate the plan")
    days: int = Field(..., ge=1, description="Number of days in itinerary")
    itinerary: List[Dict[str, Any]] = Field(default_factory=list, description="Structured itinerary by day")
    destination: Optional[str] = Field(None, description="Destination or theme")
    budget: Optional[str] = Field(None, description="Budget level: shoestring, standard, luxury")
