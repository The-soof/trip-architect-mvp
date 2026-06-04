"""Multi-modal travel-journey engine.

Turns a selected route into several persona-tailored, door-to-door journeys —
each an ordered chain of transport segments (flight, ferry, train, car, transfer)
with its own deep link. Flight data comes from a swappable provider seam
(SerpApi for accurate times/price, Travelpayouts for affiliate links, or a
deterministic generator fallback when no keys are configured).
"""

from app.services.travel.journey_builder import build_travel_journeys

__all__ = ["build_travel_journeys"]
