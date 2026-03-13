"""Pydantic output models for structured output examples."""

from pydantic import BaseModel, Field


class WeatherAnalysis(BaseModel):
    """Structured weather analysis output."""

    city: str = Field(description="City name")
    temperature_f: float = Field(description="Temperature in Fahrenheit")
    condition: str = Field(description="Weather condition (e.g., Sunny, Rainy)")
    recommendation: str = Field(description="Activity recommendation based on weather")


class MovieReview(BaseModel):
    """Structured movie review output."""

    title: str = Field(description="Movie title")
    rating: float = Field(description="Rating out of 10", ge=0, le=10)
    genre: str = Field(description="Primary genre")
    summary: str = Field(description="Brief review summary")
    recommended: bool = Field(description="Whether the movie is recommended")
