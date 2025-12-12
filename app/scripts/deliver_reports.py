"""Cron-friendly entrypoint for scheduled report delivery."""
from app.database import SessionLocal, engine
from app.db_models import Base
from app.services.report_delivery import deliver_daily_reports


def main():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        deliver_daily_reports(db=session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
