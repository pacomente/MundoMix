from datetime import datetime, time
from zoneinfo import ZoneInfo

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


def _overnight_from_previous_day(restaurant, weekday, current):
    previous = next((h for h in restaurant.hours if h.weekday == (weekday - 1) % 7), None)
    if not previous or previous.closed:
        return False
    for start_value, end_value in (
        (previous.start_time, previous.end_time),
        (previous.start_time_2, previous.end_time_2),
    ):
        start = _parse_time(start_value)
        end = _parse_time(end_value)
        if start and end and start > end and current < end:
            return True
    return False


def restaurant_is_open(restaurant, now=None):
    now = now or datetime.now(ARG_TZ)
    weekday = now.weekday()
    current = now.time().replace(second=0, microsecond=0)

    # A previous day's overnight interval has priority after midnight. This
    # remains true even if today's schedule is marked closed or is missing.
    if _overnight_from_previous_day(restaurant, weekday, current):
        return True

    hour = next((h for h in restaurant.hours if h.weekday == weekday), None)
    if not hour or hour.closed:
        return False
    if _interval_open(current, hour.start_time, hour.end_time):
        return True
    if hour.start_time_2 and hour.end_time_2:
        return _interval_open(current, hour.start_time_2, hour.end_time_2)
    return False


def restaurant_public_status(restaurant):
    return "Abierto" if restaurant_is_open(restaurant) else "Cerrado"
