from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings
from app.services.reporting import DailyReport, WeeklyReport

env = Environment(
    loader=FileSystemLoader(settings.TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def _weasyprint_render(html: str, *, base_url: str | None = None) -> bytes:
    """
    Render HTML to PDF bytes using WeasyPrint when available.

    We intentionally soft-fail when the optional dependency is missing (e.g.,
    during offline development) and let the caller fall back to a simpler
    renderer.
    """

    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return b""

    try:
        return HTML(string=html, base_url=base_url).write_pdf()
    except Exception:
        return b""


def _format_mmss(seconds: float) -> str:
    if seconds is None:
        return ""
    if seconds < 0:
        seconds = 0
    minutes = int(seconds // 60)
    secs = int(round(seconds - minutes * 60))
    return f"{minutes:02d}:{secs:02d}"

CSV_HEADERS = [
    "date",
    "session_count",
    "total_active_seconds",
    "total_raw_seconds",
    "daily_pace_label",
    "daily_pace_emoji",
]


def _total_raw_seconds(session_summaries) -> float:
    return sum(s.total_raw_seconds for s in session_summaries)


def _daily_report_row(report: DailyReport) -> list[str | float]:
    return [
        report.day_summary.date.date().isoformat(),
        report.day_summary.total_sessions,
        float(report.day_summary.total_active_seconds),
        float(_total_raw_seconds(report.session_summaries)),
        report.day_summary.daily_pace_label,
        report.day_summary.daily_pace_emoji,
    ]


def _rows_to_csv(rows: Iterable[Iterable[str | float]]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def daily_report_to_csv(report: DailyReport) -> str:
    """Render a DailyReport into a CSV string."""

    return _rows_to_csv([_daily_report_row(report)])


def weekly_report_to_csv(report: WeeklyReport) -> str:
    """Render a WeeklyReport into a CSV string including a totals row."""

    rows = [_daily_report_row(r) for r in report.daily_reports]

    total_raw_seconds = sum(_total_raw_seconds(r.session_summaries) for r in report.daily_reports)

    rows.append(
        [
            "TOTAL",
            report.totals.get("total_sessions", 0),
            float(report.totals.get("total_active_seconds", 0.0)),
            float(total_raw_seconds),
            "",
            "",
        ]
    )

    return _rows_to_csv(rows)


def _render_template(name: str, context: dict) -> str:
    template = env.get_template(name)
    return template.render(**context)


def _html_to_plain_text(html: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</(p|div|section|table|thead|tbody|tr|h[1-6])>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"[\t ]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cleaned.strip()


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _html_to_pdf_bytes(html: str) -> bytes:
    base_url = str(Path(settings.TEMPLATES_DIR).resolve())
    rendered = _weasyprint_render(html, base_url=base_url)

    if rendered:
        return rendered

    plain_text = _html_to_plain_text(html)
    lines = plain_text.splitlines() or ["(empty report)"]

    buffer = BytesIO()
    buffer.write(b"%PDF-1.4\n")

    contents = []
    y = 780
    for line in lines:
        contents.append(
            f"BT /F1 10 Tf 40 {y} Td ({_escape_pdf_text(line)}) Tj ET"
        )
        y -= 14
        if y < 40:
            y = 780

    content_stream = "\n".join(contents)
    content_bytes = content_stream.encode("utf-8")

    objects = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n{content_stream}\nendstream\nendobj\n",
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    offsets: list[int] = []
    for obj in objects:
        offsets.append(buffer.tell())
        buffer.write(obj.encode("utf-8"))

    xref_start = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode())
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets:
        buffer.write(f"{offset:010} 00000 n \n".encode())
    buffer.write(
        "trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".format(
            size=len(objects) + 1, start=xref_start
        ).encode()
    )

    return buffer.getvalue()


def _metadata_context(
    *,
    user_name: str,
    user_timezone: str,
    generated_at: datetime | None = None,
) -> dict:
    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(tz)

    return {
        "user_name": user_name,
        "timezone": user_timezone or "UTC",
        "generated_at": generated_at,
        "generated_at_label": generated_at.strftime("%Y-%m-%d %H:%M %Z"),
    }


def render_daily_report_html(
    report: DailyReport,
    *,
    user_name: str,
    user_timezone: str,
    generated_at: datetime | None = None,
) -> str:
    metadata = _metadata_context(
        user_name=user_name, user_timezone=user_timezone, generated_at=generated_at
    )

    hourly_buckets = [
        {
            "hour": bucket.hour,
            "total_questions": bucket.total_questions,
            "active_seconds": bucket.active_seconds,
            "active_mmss": _format_mmss(bucket.active_seconds),
        }
        for bucket in report.day_summary.hourly_activity
    ]

    context = {
        "metadata": metadata,
        "summary": report.day_summary,
        "session_summaries": report.session_summaries,
        "hourly_buckets": hourly_buckets,
    }

    return _render_template("reports/daily.html", context)


def render_weekly_report_html(
    report: WeeklyReport,
    *,
    user_name: str,
    user_timezone: str,
    generated_at: datetime | None = None,
) -> str:
    metadata = _metadata_context(
        user_name=user_name, user_timezone=user_timezone, generated_at=generated_at
    )

    daily_rows = [
        {
            "date": daily.date,
            "summary": daily.day_summary,
            "sessions": daily.session_summaries,
        }
        for daily in report.daily_reports
    ]

    week_end_inclusive = report.week_end - timedelta(days=1)

    context = {
        "metadata": metadata,
        "week_start": report.week_start,
        "week_start_label": report.week_start.strftime("%Y-%m-%d"),
        "week_end": report.week_end,
        "week_end_label": week_end_inclusive.strftime("%Y-%m-%d"),
        "daily_reports": daily_rows,
        "totals": report.totals,
    }

    return _render_template("reports/weekly.html", context)


def daily_report_to_pdf(
    report: DailyReport,
    *,
    user_name: str,
    user_timezone: str,
    generated_at: datetime | None = None,
) -> bytes:
    html = render_daily_report_html(
        report,
        user_name=user_name,
        user_timezone=user_timezone,
        generated_at=generated_at,
    )
    return _html_to_pdf_bytes(html)


def weekly_report_to_pdf(
    report: WeeklyReport,
    *,
    user_name: str,
    user_timezone: str,
    generated_at: datetime | None = None,
) -> bytes:
    html = render_weekly_report_html(
        report,
        user_name=user_name,
        user_timezone=user_timezone,
        generated_at=generated_at,
    )
    return _html_to_pdf_bytes(html)
