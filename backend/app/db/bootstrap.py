from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.models import ConfirmedBooking


def ensure_runtime_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())

        if "flight_options" in existing_tables:
            flight_columns = {column["name"] for column in inspector.get_columns("flight_options")}
            if "match_reason" not in flight_columns:
                connection.execute(text("ALTER TABLE flight_options ADD COLUMN match_reason TEXT DEFAULT ''"))
                connection.execute(text("UPDATE flight_options SET match_reason = '' WHERE match_reason IS NULL"))

        if "hotel_options" in existing_tables:
            hotel_columns = {column["name"] for column in inspector.get_columns("hotel_options")}
            if "match_reason" not in hotel_columns:
                connection.execute(text("ALTER TABLE hotel_options ADD COLUMN match_reason TEXT DEFAULT ''"))
                connection.execute(text("UPDATE hotel_options SET match_reason = '' WHERE match_reason IS NULL"))

        if "saved_trips" in existing_tables:
            saved_trip_columns = {column["name"] for column in inspector.get_columns("saved_trips")}
            if "confirmed_booking_count" not in saved_trip_columns:
                connection.execute(text("ALTER TABLE saved_trips ADD COLUMN confirmed_booking_count INTEGER DEFAULT 0"))
                connection.execute(text("UPDATE saved_trips SET confirmed_booking_count = 0 WHERE confirmed_booking_count IS NULL"))

        if "confirmed_bookings" not in existing_tables:
            ConfirmedBooking.__table__.create(bind=connection, checkfirst=True)
