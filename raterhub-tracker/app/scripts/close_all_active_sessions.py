# app/scripts/close_all_active_sessions.py

from datetime import datetime

from app.database import SessionLocal
from app.db_models import Session as DbSession


def main():
    db = SessionLocal()
    now = datetime.utcnow()

    try:
        active_sessions = (
            db.query(DbSession)
            .filter(DbSession.is_active == True)
            .all()
        )

        print(f"Found {len(active_sessions)} active session(s).")

        for s in active_sessions:
            print(
                f"- Closing session id={s.id}, public_id={s.public_id}, "
                f"user_id={s.user_id}, started_at={s.started_at}, ended_at={s.ended_at}"
            )
            s.is_active = False
            if s.ended_at is None:
                s.ended_at = now

            # Clean up state fields so they don't affect future logic
            s.current_question_started_at = None
            s.pause_accumulated_seconds = 0.0
            s.is_paused = False
            s.pause_started_at = None

        db.commit()
        print("All active sessions have been closed.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
