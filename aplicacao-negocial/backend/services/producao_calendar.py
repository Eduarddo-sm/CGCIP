from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException, status

def month_range(reference: date) -> tuple[date, date]:
    start = date(reference.year, reference.month, 1)
    if reference.month == 12:
        end = date(reference.year + 1, 1, 1)
    else:
        end = date(reference.year, reference.month + 1, 1)
    return start, end


def current_month_start(reference: date | None = None) -> date:
    today = reference or date.today()
    return date(today.year, today.month, 1)


def previous_month_start(reference: date | None = None) -> date:
    current = current_month_start(reference)
    return date(current.year - 1, 12, 1) if current.month == 1 else date(current.year, current.month - 1, 1)


def _national_holidays(year: int) -> set[date]:
    return {
        date(year, 1, 1),
        date(year, 4, 21),
        date(year, 5, 1),
        date(year, 9, 7),
        date(year, 10, 12),
        date(year, 11, 2),
        date(year, 11, 15),
        date(year, 11, 20),
        date(year, 12, 25),
    }


def second_business_day(reference: date | None = None, holidays: set[date] | None = None) -> date:
    current = current_month_start(reference)
    excluded = _national_holidays(current.year) | (holidays or set())
    cursor = current
    found = 0
    while True:
        if cursor.weekday() < 5 and cursor not in excluded:
            found += 1
            if found == 2:
                return cursor
        cursor += timedelta(days=1)


def rollover_deadline_reached(reference: date | None = None, holidays: set[date] | None = None) -> bool:
    today = reference or date.today()
    return today >= second_business_day(today, holidays)


def _first_day_next_month(reference: date) -> date:
    if reference.month == 12:
        return date(reference.year + 1, 1, 1)
    return date(reference.year, reference.month + 1, 1)


def _last_day_of_month(reference: date) -> date:
    return _first_day_next_month(reference) - timedelta(days=1)


def can_move_to_next_month(reference: date | None = None) -> bool:
    today = reference or date.today()
    days_until_close = (_last_day_of_month(today) - today).days
    return 0 <= days_until_close <= 5


def resolve_production_date(jogar_proximo_mes: bool) -> date:
    today = date.today()
    if not jogar_proximo_mes:
        return today
    if not can_move_to_next_month(today):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Jogar para o proximo mes fica disponivel apenas nos ultimos 5 dias antes do fechamento do mes.",
        )
    return _first_day_next_month(today)
