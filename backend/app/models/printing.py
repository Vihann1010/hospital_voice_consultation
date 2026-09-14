"""How each printed document looks.

Every document this hospital hands a patient — bill, prescription, lab report,
discharge summary — is printed on the same letterhead and has to line up with
whatever pre-printed stationery is in the tray. That is a property of the
hospital and its printer, not of the code, so it is configured rather than
compiled: margins move when the letterhead changes, and nobody should need a
deployment to stop the header overprinting the logo.

One row per document type. A type with no row uses the defaults below, so a
new kind of document prints sensibly before anyone has configured it.
"""
from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PrintSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "print_settings"

    # invoice | receipt | prescription | lab_report | discharge_summary | ...
    document_type: Mapped[str] = mapped_column(
        String(48), nullable=False, unique=True, index=True
    )

    # Points, matching ReportLab's unit. A4 is 595 x 842.
    margin_top: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    margin_bottom: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    margin_left: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    margin_right: Mapped[int] = mapped_column(Integer, nullable=False, default=42)

    font_family: Mapped[str] = mapped_column(String(64), nullable=False, default="Helvetica")
    font_size: Mapped[int] = mapped_column(Integer, nullable=False, default=9)

    # Filenames under MEDIA_ROOT/branding. Hospitals print onto pre-printed
    # letterhead as often as not, so both are optional and their heights are
    # configurable — the space has to be reserved even when nothing is drawn
    # into it, or the text lands on top of the printed header.
    header_image: Mapped[Optional[str]] = mapped_column(String(255))
    header_height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    footer_image: Mapped[Optional[str]] = mapped_column(String(255))
    footer_height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Printed small at the foot of every page of this document type.
    footer_remark: Mapped[Optional[str]] = mapped_column(Text)

    # Whether a reprint is stamped. Kept per document type because a duplicate
    # bill must be marked to be worth anything to an auditor, while a
    # reprinted prescription usually should not be.
    watermark_duplicates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
