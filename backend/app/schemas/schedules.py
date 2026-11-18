# Backwards-compatible import. Schedule schemas live in schedule.py.
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate, ScheduleResponse

__all__ = ["ScheduleCreate", "ScheduleUpdate", "ScheduleResponse"]
