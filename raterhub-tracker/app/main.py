def build_day_summary(
    db: OrmSession,
    user: User,
    target_date: datetime,
) -> TodaySummary:
    """
    Build a summary for a given calendar date (UTC).
    """
    day_start = datetime(target_date.year, target_date.month, target_date.day)
    day_end = day_start + timedelta(days=1)

    sessions = (
        db.query(DbSession)
        .filter(
            DbSession.user_id == user.id,
            DbSession.started_at >= day_start,
            DbSession.started_at < day_end,
        )
        .order_by(DbSession.started_at.asc())
        .all()
    )

    if not sessions:
        return TodaySummary(
            date=day_start,
            user_external_id=user.email,
            total_sessions=0,
            total_questions=0,
            total_active_seconds=0.0,
            total_active_mmss="00:00",
            sessions=[],
        )

    total_sessions = 0
    total_questions_all = 0
    total_active_all = 0.0
    items: List[TodaySessionItem] = []

    for s in sessions:
        all_questions = (
            db.query(Question)
            .filter(Question.session_id == s.id)
            .order_by(Question.index.asc())
            .all()
        )

        # Filter out ghost entries
        qs = [q for q in all_questions if not is_ghost_question(q)]

        if not qs:
            items.append(
                TodaySessionItem(
                    session_id=s.public_id,
                    started_at=s.started_at,
                    ended_at=s.ended_at,
                    is_active=s.is_active,
                    total_questions=0,
                    total_active_seconds=0.0,
                    avg_active_seconds=0.0,
                    avg_active_mmss="00:00",
                    pace_label="No questions",
                    pace_emoji="😴",
                    score=0,
                )
            )
            total_sessions += 1
            continue

        total_sessions += 1

        total_active = sum(q.active_seconds for q in qs)
        count = len(qs)
        avg_active = total_active / count if count else 0.0

        pace = compute_pace(avg_active, s.target_minutes_per_question or 5.5)

        total_questions_all += count
        total_active_all += total_active

        items.append(
            TodaySessionItem(
                session_id=s.public_id,
                started_at=s.started_at,
                ended_at=s.ended_at,
                is_active=s.is_active,
                total_questions=count,
                total_active_seconds=total_active,
                avg_active_seconds=avg_active,
                avg_active_mmss=format_mmss(avg_active),
                pace_label=pace["pace_label"],
                pace_emoji=pace["pace_emoji"],
                score=pace["score"],
            )
        )

    return TodaySummary(
        date=day_start,
        user_external_id=user.email,
        total_sessions=total_sessions,
        total_questions=total_questions_all,
        total_active_seconds=total_active_all,
        total_active_mmss=format_mmss(total_active_all),
        sessions=items,
    )
