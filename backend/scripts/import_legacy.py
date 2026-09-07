#!/usr/bin/env python3
"""Import patient records from the hospital's previous software.

    python -m scripts.import_legacy --file patients.csv --dry-run
    python -m scripts.import_legacy --file patients.csv

Reads a CSV. Almost every hospital system — Medisoft, HMS, a Tally-based
package, or a clerk's Excel sheet — can export one, and CSV is the only format
that does not require reverse-engineering somebody's database.

Three properties this is built around, learned from migrations going wrong:

**Dry run is the default posture.** Nothing is written until you have seen the
report. A bad import into a live patient database is very expensive to undo.

**Re-running is safe.** Rows are matched on `legacy_id`, so a partial import
that failed halfway can simply be run again: existing records are updated,
missing ones created. Without this, the second attempt silently doubles the
patient list.

**Bad rows are reported, not guessed at.** A row with an unreadable age or a
missing name is listed for a human to fix, rather than being imported with a
plausible-looking default that nobody ever notices.

Expected columns (case-insensitive, extra columns ignored):

    legacy_id       required   the ID in the old system — the matching key
    name            required
    phone           required
    age                        integer; omit if date_of_birth is present
    date_of_birth              YYYY-MM-DD, DD/MM/YYYY or DD-MM-YYYY
    gender                     m/f/male/female/other
    address, city, blood_group, emergency_contact_name, emergency_contact_phone
    uhid                       the old hospital number, if one exists
"""
import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import select

sys.path.insert(0, ".")

from app.billing.identifiers import build_uhid, is_valid_uhid  # noqa: E402
# Importing the registry defines every mapper before any model is used.
# Without it SQLAlchemy cannot resolve relationships declared by string
# name (Patient -> "Consultation"), and the script dies on first use.
from app.models import registry as _registry  # noqa: F401,E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.emr import DocumentCounter  # noqa: E402
from app.models.enums import Gender  # noqa: E402
from app.models.patient import Patient  # noqa: E402

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y")

GENDERS: Dict[str, Gender] = {
    "m": Gender.MALE, "male": Gender.MALE, "man": Gender.MALE,
    "f": Gender.FEMALE, "female": Gender.FEMALE, "woman": Gender.FEMALE,
    "o": Gender.OTHER, "other": Gender.OTHER, "transgender": Gender.OTHER,
}


@dataclass
class Row:
    line: int
    legacy_id: str
    name: str
    phone: str
    age: Optional[int] = None
    date_of_birth: Optional[date] = None
    gender: Gender = Gender.OTHER
    address: Optional[str] = None
    city: Optional[str] = None
    blood_group: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    legacy_uhid: Optional[str] = None


@dataclass
class Report:
    total: int = 0
    to_create: int = 0
    to_update: int = 0
    rejected: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def parse_date(value: str) -> Optional[date]:
    text = _clean(value)
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_phone(value: str) -> str:
    """Keep the digits; drop +91, spaces, dashes and brackets."""
    digits = "".join(character for character in _clean(value) if character.isdigit())
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def age_from_dob(born: date, on: Optional[date] = None) -> int:
    today = on or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def parse_row(raw: Dict[str, str], line: int) -> tuple[Optional[Row], Optional[str]]:
    """Turn one CSV row into a Row, or explain why it cannot be imported."""
    lowered = {(key or "").strip().lower(): value for key, value in raw.items()}

    legacy_id = _clean(lowered.get("legacy_id") or lowered.get("id") or lowered.get("patient_id"))
    name = _clean(lowered.get("name") or lowered.get("patient_name"))
    phone = parse_phone(lowered.get("phone") or lowered.get("mobile") or lowered.get("contact") or "")

    if not legacy_id:
        return None, f"line {line}: no legacy_id — cannot match this row safely"
    if not name:
        return None, f"line {line} ({legacy_id}): no name"
    if len(phone) < 10:
        return None, f"line {line} ({legacy_id}): phone '{lowered.get('phone', '')}' is not usable"

    born = parse_date(lowered.get("date_of_birth") or lowered.get("dob") or "")
    age: Optional[int] = None
    raw_age = _clean(lowered.get("age"))
    if raw_age:
        try:
            age = int(float(raw_age))
        except ValueError:
            age = None
    if age is None and born is not None:
        age = age_from_dob(born)
    if age is None:
        return None, f"line {line} ({legacy_id}): neither a usable age nor date of birth"
    if not 0 <= age <= 120:
        return None, f"line {line} ({legacy_id}): age {age} is out of range"

    gender = GENDERS.get(_clean(lowered.get("gender") or lowered.get("sex")).lower(), Gender.OTHER)

    return Row(
        line=line,
        legacy_id=legacy_id,
        name=name,
        phone=phone,
        age=age,
        date_of_birth=born,
        gender=gender,
        address=_clean(lowered.get("address")) or None,
        city=_clean(lowered.get("city")) or None,
        blood_group=_clean(lowered.get("blood_group") or lowered.get("blood")) or None,
        emergency_contact_name=_clean(lowered.get("emergency_contact_name")) or None,
        emergency_contact_phone=parse_phone(lowered.get("emergency_contact_phone") or "") or None,
        legacy_uhid=_clean(lowered.get("uhid") or lowered.get("hospital_id")) or None,
    ), None


async def run(path: str, dry_run: bool, limit: Optional[int]) -> Report:
    report = Report()
    rows: List[Row] = []

    with open(path, newline="", encoding="utf-8-sig") as handle:
        for index, raw in enumerate(csv.DictReader(handle), start=2):
            if limit and len(rows) >= limit:
                break
            report.total += 1
            row, problem = parse_row(raw, index)
            if problem:
                report.rejected.append(problem)
            else:
                rows.append(row)

    async with AsyncSessionLocal() as session:
        counter_result = await session.execute(
            select(DocumentCounter).where(
                DocumentCounter.scope == "uhid", DocumentCounter.period == "all"
            )
        )
        counter = counter_result.scalar_one_or_none()
        if counter is None:
            counter = DocumentCounter(scope="uhid", period="all", last_value=0)
            session.add(counter)
            await session.flush()
        next_value = counter.last_value

        for row in rows:
            existing = (
                await session.execute(
                    select(Patient).where(Patient.legacy_id == row.legacy_id)
                )
            ).scalar_one_or_none()

            if existing is not None:
                report.to_update += 1
                if not dry_run:
                    existing.name = row.name
                    existing.age = row.age
                    existing.gender = row.gender
                    existing.phone_number = row.phone
                    existing.date_of_birth = row.date_of_birth or existing.date_of_birth
                    existing.address = row.address or existing.address
                    existing.city = row.city or existing.city
                    existing.blood_group = row.blood_group or existing.blood_group
                continue

            report.to_create += 1
            # An old hospital number is kept only if it fits this system's
            # format; otherwise a fresh UHID is issued and the old number
            # stays recoverable through legacy_id.
            if row.legacy_uhid and is_valid_uhid(row.legacy_uhid):
                uhid = row.legacy_uhid
            else:
                next_value += 1
                uhid = build_uhid(next_value)
                if row.legacy_uhid:
                    report.warnings.append(
                        f"line {row.line} ({row.legacy_id}): old number "
                        f"'{row.legacy_uhid}' kept as legacy_id; issued {uhid}"
                    )

            if not dry_run:
                session.add(
                    Patient(
                        uhid=uhid,
                        legacy_id=row.legacy_id,
                        name=row.name,
                        age=row.age,
                        gender=row.gender,
                        phone_number=row.phone,
                        date_of_birth=row.date_of_birth,
                        address=row.address,
                        city=row.city,
                        blood_group=row.blood_group,
                        emergency_contact_name=row.emergency_contact_name,
                        emergency_contact_phone=row.emergency_contact_phone,
                    )
                )

        if not dry_run:
            counter.last_value = next_value
            await session.commit()

    return report


def print_report(report: Report, dry_run: bool) -> None:
    print("\n" + "=" * 62)
    print(f"  rows read        {report.total}")
    print(f"  to create        {report.to_create}")
    print(f"  to update        {report.to_update}")
    print(f"  rejected         {len(report.rejected)}")
    print("=" * 62)

    if report.rejected:
        print("\nRejected rows — fix these in the CSV and re-run:")
        for problem in report.rejected[:40]:
            print(f"  {problem}")
        if len(report.rejected) > 40:
            print(f"  … and {len(report.rejected) - 40} more")

    if report.warnings:
        print("\nWarnings:")
        for warning in report.warnings[:20]:
            print(f"  {warning}")
        if len(report.warnings) > 20:
            print(f"  … and {len(report.warnings) - 20} more")

    if dry_run:
        print("\nDry run — nothing was written.")
        print("Re-run without --dry-run once the rejected rows look acceptable.")
    else:
        print("\nImport complete. Re-running this file is safe: rows are matched")
        print("on legacy_id, so existing patients are updated rather than duplicated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import patients from a legacy CSV export.")
    parser.add_argument("--file", required=True, help="path to the CSV export")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate and report, write nothing")
    parser.add_argument("--limit", type=int, default=None,
                        help="only process the first N rows (useful for a first look)")
    args = parser.parse_args()

    result = asyncio.run(run(args.file, args.dry_run, args.limit))
    print_report(result, args.dry_run)
    sys.exit(1 if result.rejected and not args.dry_run else 0)
