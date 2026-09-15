from datetime import datetime, time
from zoneinfo import ZoneInfo
from flask import current_app


ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _parse_time(value):
    try:
        hour, minute = (int(x) for x in (value or "").split(":", 1))
        return time(hour, minute)
    except (ValueError, TypeError):
        return None


def _interval_open(now, start_value, end_value):
    start = _parse_time(start_value)
    end = _parse_time(end_value)
    if not start or not end:
        return False
    if start == end:
        return True
    if start < end:
        return start <= now < end
    return now >= start or now < end


def restaurant_is_open(restaurant, now=None):
    now = now or datetime.now(ARG_TZ)
    weekday = now.weekday()
    hour = next((h for h in restaurant.hours if h.weekday == weekday), None)
    if not hour or hour.closed:
        return False
    current = now.time().replace(second=0, microsecond=0)
    if _interval_open(current, hour.start_time, hour.end_time):
        return True
    if hour.start_time_2 and hour.end_time_2:
        return _interval_open(current, hour.start_time_2, hour.end_time_2)
    # Overnight windows belong to the previous day's schedule after midnight.
    previous = next((h for h in restaurant.hours if h.weekday == (weekday - 1) % 7), None)
    if previous and not previous.closed and previous.start_time and previous.end_time:
        start = _parse_time(previous.start_time)
        end = _parse_time(previous.end_time)
        if start and end and start > end and current < end:
            return True
        if previous.start_time_2 and previous.end_time_2:
            start2 = _parse_time(previous.start_time_2)
            end2 = _parse_time(previous.end_time_2)
            if start2 and end2 and start2 > end2 and current < end2:
                return True
    return False


def restaurant_public_status(restaurant):
    return "Abierto" if restaurant_is_open(restaurant) else "Cerrado"
