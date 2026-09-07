"""Data access for the investigation module."""
import uuid
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from app.models.enums import OrderStatus, ReportStatus
from app.models.investigation import (
    DoctorFavoriteInvestigation,
    InvestigationOrder,
    InvestigationOrderItem,
    InvestigationReport,
    InvestigationTemplate,
)
from app.repositories.base import BaseRepository


class InvestigationOrderRepository(BaseRepository[InvestigationOrder]):
    model = InvestigationOrder

    async def get_with_items(self, order_id: uuid.UUID) -> Optional[InvestigationOrder]:
        result = await self.session.execute(
            select(InvestigationOrder)
            .options(
                selectinload(InvestigationOrder.items),
                selectinload(InvestigationOrder.reports),
            )
            .where(InvestigationOrder.id == order_id)
        )
        return result.scalar_one_or_none()

    async def list_for(
        self,
        *,
        patient_id: Optional[uuid.UUID] = None,
        consultation_id: Optional[uuid.UUID] = None,
        limit: int = 50,
    ) -> List[InvestigationOrder]:
        statement = (
            select(InvestigationOrder)
            .options(selectinload(InvestigationOrder.items))
            .order_by(desc(InvestigationOrder.created_at))
            .limit(limit)
        )
        if patient_id is not None:
            statement = statement.where(InvestigationOrder.patient_id == patient_id)
        if consultation_id is not None:
            statement = statement.where(InvestigationOrder.consultation_id == consultation_id)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def recently_used_codes(
        self, *, user_id: uuid.UUID, limit: int = 12
    ) -> List[Tuple[str, str, int]]:
        """(code, name, times ordered) for this clinician, most recent first.

        Ordered by the latest use rather than raw frequency, so a doctor's
        current working set surfaces ahead of something ordered often last year.
        """
        result = await self.session.execute(
            select(
                InvestigationOrderItem.code,
                func.max(InvestigationOrderItem.name).label("name"),
                func.count(InvestigationOrderItem.id).label("uses"),
                func.max(InvestigationOrderItem.created_at).label("last_used"),
            )
            .join(InvestigationOrder, InvestigationOrderItem.order_id == InvestigationOrder.id)
            .where(InvestigationOrder.ordered_by_id == user_id)
            .group_by(InvestigationOrderItem.code)
            .order_by(desc("last_used"))
            .limit(limit)
        )
        return [(row[0], row[1], int(row[2])) for row in result.all()]

    async def mark_items_reported(self, order_id: uuid.UUID) -> None:
        """Advance an order's status once reports start arriving."""
        order = await self.get_with_items(order_id)
        if order is None:
            return
        has_reports = any(
            report.status != ReportStatus.SUPERSEDED for report in order.reports
        )
        if not has_reports:
            return
        order.status = (
            OrderStatus.COMPLETED
            if all(item.reported for item in order.items)
            else OrderStatus.PARTIALLY_REPORTED
        )
        await self.session.flush()


class InvestigationReportRepository(BaseRepository[InvestigationReport]):
    model = InvestigationReport

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, current_only: bool = True, limit: int = 100
    ) -> List[InvestigationReport]:
        statement = (
            select(InvestigationReport)
            .where(InvestigationReport.patient_id == patient_id)
            .order_by(desc(InvestigationReport.created_at))
            .limit(limit)
        )
        if current_only:
            statement = statement.where(InvestigationReport.status != ReportStatus.SUPERSEDED)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_for_consultation(
        self, consultation_id: uuid.UUID, *, current_only: bool = True
    ) -> List[InvestigationReport]:
        statement = (
            select(InvestigationReport)
            .where(InvestigationReport.consultation_id == consultation_id)
            .order_by(desc(InvestigationReport.created_at))
        )
        if current_only:
            statement = statement.where(InvestigationReport.status != ReportStatus.SUPERSEDED)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def version_history(self, group_id: uuid.UUID) -> List[InvestigationReport]:
        """Every version in a group, newest first."""
        result = await self.session.execute(
            select(InvestigationReport)
            .where(InvestigationReport.group_id == group_id)
            .order_by(desc(InvestigationReport.version))
        )
        return list(result.scalars().all())

    async def latest_in_group(self, group_id: uuid.UUID) -> Optional[InvestigationReport]:
        result = await self.session.execute(
            select(InvestigationReport)
            .where(InvestigationReport.group_id == group_id)
            .order_by(desc(InvestigationReport.version))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_duplicate(
        self, patient_id: uuid.UUID, checksum: str
    ) -> Optional[InvestigationReport]:
        """Same bytes already uploaded for this patient."""
        result = await self.session.execute(
            select(InvestigationReport)
            .where(
                InvestigationReport.patient_id == patient_id,
                InvestigationReport.checksum_sha256 == checksum,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


class InvestigationPreferenceRepository:
    """Favourites and saved templates."""

    def __init__(self, session) -> None:
        self.session = session

    async def favorites(self, user_id: uuid.UUID) -> List[str]:
        result = await self.session.execute(
            select(DoctorFavoriteInvestigation.code)
            .where(DoctorFavoriteInvestigation.user_id == user_id)
            .order_by(DoctorFavoriteInvestigation.created_at)
        )
        return [row[0] for row in result.all()]

    async def add_favorite(self, user_id: uuid.UUID, code: str) -> None:
        existing = await self.session.execute(
            select(DoctorFavoriteInvestigation).where(
                DoctorFavoriteInvestigation.user_id == user_id,
                DoctorFavoriteInvestigation.code == code,
            )
        )
        if existing.scalar_one_or_none() is None:
            self.session.add(DoctorFavoriteInvestigation(user_id=user_id, code=code))
            await self.session.flush()

    async def remove_favorite(self, user_id: uuid.UUID, code: str) -> None:
        existing = await self.session.execute(
            select(DoctorFavoriteInvestigation).where(
                DoctorFavoriteInvestigation.user_id == user_id,
                DoctorFavoriteInvestigation.code == code,
            )
        )
        record = existing.scalar_one_or_none()
        if record is not None:
            await self.session.delete(record)
            await self.session.flush()

    async def templates(self, user_id: uuid.UUID, department) -> List[InvestigationTemplate]:
        """A doctor's own templates plus those shared with their department."""
        from sqlalchemy import or_

        conditions = [InvestigationTemplate.user_id == user_id]
        if department is not None:
            conditions.append(
                (InvestigationTemplate.user_id.is_(None))
                & (InvestigationTemplate.department == department)
            )
        else:
            conditions.append(InvestigationTemplate.user_id.is_(None))
        result = await self.session.execute(
            select(InvestigationTemplate)
            .where(or_(*conditions))
            .order_by(InvestigationTemplate.name)
        )
        return list(result.scalars().all())

    async def get_template(self, template_id: uuid.UUID) -> Optional[InvestigationTemplate]:
        result = await self.session.execute(
            select(InvestigationTemplate).where(InvestigationTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def create_template(self, template: InvestigationTemplate) -> InvestigationTemplate:
        self.session.add(template)
        await self.session.flush()
        return template

    async def delete_template(self, template: InvestigationTemplate) -> None:
        await self.session.delete(template)
        await self.session.flush()
