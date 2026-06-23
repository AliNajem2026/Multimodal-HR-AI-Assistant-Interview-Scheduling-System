import datetime
import pytest
from app.routers.scheduler import _generate_week_slots, _week_label


class TestGenerateWeekSlots:
    def test_always_returns_three_slots(self):
        assert len(_generate_week_slots(0)) == 3
        assert len(_generate_week_slots(1)) == 3
        assert len(_generate_week_slots(3)) == 3

    def test_slots_are_on_monday_wednesday_friday(self):
        slots = _generate_week_slots(0)
        dts = [datetime.datetime.fromisoformat(s) for s in slots]
        assert dts[0].weekday() == 0, "First slot should be Monday"
        assert dts[1].weekday() == 2, "Second slot should be Wednesday"
        assert dts[2].weekday() == 4, "Third slot should be Friday"

    def test_slots_are_at_correct_hours(self):
        slots = _generate_week_slots(0)
        dts = [datetime.datetime.fromisoformat(s) for s in slots]
        assert dts[0].hour == 10, "Monday slot should be 10:00 AM"
        assert dts[1].hour == 14, "Wednesday slot should be 2:00 PM"
        assert dts[2].hour == 16, "Friday slot should be 4:00 PM"

    def test_all_slots_are_in_the_future(self):
        now = datetime.datetime.now()
        for slot in _generate_week_slots(0):
            assert datetime.datetime.fromisoformat(slot) > now

    def test_week_offset_shifts_slots_by_exactly_seven_days(self):
        slots_0 = _generate_week_slots(0)
        slots_1 = _generate_week_slots(1)
        for s0, s1 in zip(slots_0, slots_1):
            dt0 = datetime.datetime.fromisoformat(s0)
            dt1 = datetime.datetime.fromisoformat(s1)
            assert (dt1 - dt0).days == 7

    def test_slots_are_iso_format_strings(self):
        for slot in _generate_week_slots(0):
            # fromisoformat raises ValueError if the string is not valid ISO
            datetime.datetime.fromisoformat(slot)

    def test_minutes_and_seconds_are_zero(self):
        for slot in _generate_week_slots(0):
            dt = datetime.datetime.fromisoformat(slot)
            assert dt.minute == 0
            assert dt.second == 0


class TestWeekLabel:
    def test_offset_zero_returns_next_week(self):
        assert _week_label(0) == "next week"

    def test_offset_one_returns_week_after_next(self):
        assert _week_label(1) == "the week after next"

    def test_offset_two_returns_three_weeks_from_now(self):
        assert _week_label(2) == "3 weeks from now"

    def test_offset_five_returns_six_weeks_from_now(self):
        assert _week_label(5) == "6 weeks from now"
