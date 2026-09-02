from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import User, UserMonthlyGoal


def month_start(value: date | str | None = None) -> date:
    if value is None:
        current = date.today()
        return current.replace(day=1)
    if isinstance(value, date):
        return value.replace(day=1)
    text = str(value).strip()
    try:
        year, month = (int(part) for part in text[:7].split("-"))
        return date(year, month, 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("Competencia invalida. Use o formato AAAA-MM.") from exc


def effective_goal(db: Session, user: User, competencia: date | str | None = None) -> Decimal:
    target = month_start(competencia)
    goal = db.scalar(
        select(UserMonthlyGoal.meta_pagamento).where(
            UserMonthlyGoal.user_id == user.id,
            UserMonthlyGoal.competencia == target,
        )
    )
    if goal is not None:
        return Decimal(goal)
    fallback = Decimal(user.meta_pagamento or 0)
    db.add(UserMonthlyGoal(user_id=user.id, competencia=target, meta_pagamento=fallback, updated_by="SISTEMA"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        goal = db.scalar(
            select(UserMonthlyGoal.meta_pagamento).where(
                UserMonthlyGoal.user_id == user.id,
                UserMonthlyGoal.competencia == target,
            )
        )
        return Decimal(goal if goal is not None else fallback)
    return fallback


def set_goal(
    db: Session,
    user: User,
    competencia: date | str,
    meta_pagamento: Decimal | float,
    updated_by: str | None = None,
) -> UserMonthlyGoal:
    target = month_start(competencia)
    goal = db.scalar(
        select(UserMonthlyGoal).where(
            UserMonthlyGoal.user_id == user.id,
            UserMonthlyGoal.competencia == target,
        )
    )
    if goal is None:
        goal = UserMonthlyGoal(user_id=user.id, competencia=target, meta_pagamento=meta_pagamento)
        db.add(goal)
    else:
        goal.meta_pagamento = meta_pagamento
    goal.updated_by = updated_by
    if target == month_start():
        user.meta_pagamento = meta_pagamento
    db.commit()
    db.refresh(goal)
    return goal


def goals_by_competence(db: Session, user: User, competences: set[str]) -> dict[str, float]:
    targets = {month_start(value) for value in competences if value}
    if not targets:
        targets = {month_start()}
    rows = db.execute(
        select(UserMonthlyGoal.competencia, UserMonthlyGoal.meta_pagamento).where(
            UserMonthlyGoal.user_id == user.id,
            UserMonthlyGoal.competencia.in_(targets),
        )
    ).all()
    found = {competencia.strftime("%Y-%m"): float(meta) for competencia, meta in rows}
    fallback = float(user.meta_pagamento or 0)
    missing = [target for target in targets if target.strftime("%Y-%m") not in found]
    if missing:
        for target in missing:
            db.add(UserMonthlyGoal(user_id=user.id, competencia=target, meta_pagamento=fallback, updated_by="SISTEMA"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        rows = db.execute(
            select(UserMonthlyGoal.competencia, UserMonthlyGoal.meta_pagamento).where(
                UserMonthlyGoal.user_id == user.id,
                UserMonthlyGoal.competencia.in_(targets),
            )
        ).all()
        found = {competencia.strftime("%Y-%m"): float(meta) for competencia, meta in rows}
    return {target.strftime("%Y-%m"): found.get(target.strftime("%Y-%m"), fallback) for target in targets}
