import os
import re
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_
from sqlmodel import select, func, text

from dotenv import load_dotenv

from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple

from ..models import Report, ReportAdded, Study, StudyAdded, StudyReport
from ..models import StudyIntervention, Intervention, StudyCondition, Condition, StudyOutcome, Outcome, StudyDesign, Design, StudyParticipant, Participant

from ...utils.postprocessing import normalize_author_names
from ...utils.dto import Tag
from ...utils.query_parser import AdvancedSearchField, AndGroup, Comparison, OrGroup, QueryNode

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

class DuplicateShortNameError(ValueError):
    pass

def load_trial_id_mapping():
    file_path = os.path.join(DATABASE_VOLUME,"resources", "trial_id_mapping.json")
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as json_file:
        return json.load(json_file)

trial_id_mapping = load_trial_id_mapping()

# Each aspect field is a study_<aspect> join table to an <aspect> table with an
# id + description column (see models.py) - maps an advanced-search field to the
# (join table's study_id column, its fk-to-aspect column, aspect table's pk, aspect
# table's description column) needed to build an EXISTS clause for it. Keyed by the
# AdvancedSearchField enum (not a raw string) - field-name validity, including
# alias/plural normalization, is already enforced by Comparison's own pydantic
# validation (src/utils/query_parser.py) before a Comparison ever reaches here, so
# there's no "unknown field" case left to check or raise for at this layer.
_ASPECT_FIELDS = {
    AdvancedSearchField.INTERVENTION: (StudyIntervention.study_id, StudyIntervention.intervention_id, Intervention.id, Intervention.description),
    AdvancedSearchField.CONDITION: (StudyCondition.study_id, StudyCondition.condition_id, Condition.id, Condition.description),
    AdvancedSearchField.OUTCOME: (StudyOutcome.study_id, StudyOutcome.outcome_id, Outcome.id, Outcome.description),
    AdvancedSearchField.PARTICIPANT: (StudyParticipant.study_id, StudyParticipant.participant_id, Participant.id, Participant.description),
    AdvancedSearchField.DESIGN: (StudyDesign.study_id, StudyDesign.design_id, Design.id, Design.description),
}

def _aspect_exists(join_study_id, join_fk_col, aspect_pk_col, aspect_desc_col, pattern):
    return (
        select(1)
        .where(join_study_id == Study.id, join_fk_col == aspect_pk_col, aspect_desc_col.ilike(pattern))
        .exists()
    )

def _comparison_to_condition(comparison: Comparison):
    field = comparison.field
    pattern = f"%{comparison.value}%"

    if field in _ASPECT_FIELDS:
        join_study_id, join_fk_col, aspect_pk_col, aspect_desc_col = _ASPECT_FIELDS[field]
        return _aspect_exists(join_study_id, join_fk_col, aspect_pk_col, aspect_desc_col, pattern)

    if field == AdvancedSearchField.AUTHOR:
        return (
            select(1)
            .where(StudyReport.study_id == Study.id, StudyReport.report_id == Report.id, Report.authors.ilike(pattern))
            .exists()
        )

    if field == AdvancedSearchField.NAME:
        return Study.short_name.ilike(pattern)

    if field == AdvancedSearchField.TRIAL_ID:
        return or_(
            Study.trial_registration_id.ilike(pattern),
            select(1).where(StudyReport.study_id == Study.id, StudyReport.report_id == Report.id, Report.trial_registration_id.ilike(pattern)).exists(),
            select(1).where(StudyReport.study_id == Study.id, StudyReport.report_id == ReportAdded.report_id, ReportAdded.trial_registration_id.ilike(pattern)).exists(),
        )

    if field == AdvancedSearchField.STATUS:
        return Study.status.ilike(pattern)

    if field == AdvancedSearchField.COUNTRY:
        return Study.countries.ilike(pattern)

    # Unreachable: AdvancedSearchField is a closed enum and every member is handled
    # above - this only trips if a new enum member is added without a case here.
    raise AssertionError(f"No SQL mapping for advanced-search field {field!r}")

def _query_node_to_condition(node: QueryNode):
    if isinstance(node, AndGroup):
        return and_(*[_query_node_to_condition(operand) for operand in node.operands])
    if isinstance(node, OrGroup):
        return or_(*[_query_node_to_condition(operand) for operand in node.operands])
    return _comparison_to_condition(node)

class StudyRepository:
    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

    async def commit(self):
        await self.db.commit()

    async def rollback(self):
        await self.db.rollback()

    async def add_study(self, short_name : str, study_status: str, countries : List[str], duration : str, number_of_participants : int, comparison : str) -> Study:
        #TODO add more sophisticated checks

        try:
            new_study = Study(
                short_name=short_name,
                status=study_status,
                countries="//".join(countries),
                duration=duration,
                number_participants=str(number_of_participants),
                comparison=comparison
            )

            self.db.add(new_study)
            await self.db.flush()

            study_added_entry = StudyAdded(
                study_id=new_study.id,
                created_by=self.user_id,
            )
            self.db.add(study_added_entry)

            await self.db.flush()
            await self.db.refresh(new_study)

            return new_study

        except IntegrityError as e:
            diag = getattr(getattr(e.orig, "__cause__", None), "diag", None)
            if getattr(diag, "constraint_name", None) == "uq_study_short_name":
                raise DuplicateShortNameError("short_name already exists")
            raise

    async def search_studies(self, query: str, limit: int, offset: int) -> Tuple[List[Study], bool]:
        """Free-text search across a study's own name/trial ID plus its linked reports'
        authors/trial ID - both the confirmed Report.trial_registration_id and the
        unconfirmed report_added.trial_registration_id guess (see their comments in
        models.py) - and interventions. Returns (page, has_more) - one extra id beyond
        the page is fetched so has_more can be determined without a separate count
        query, same convention as StudySimilaritySearchService.get_similar_studies_by_id.
        """
        pattern = f"%{query}%"
        id_stmt = (
            select(Study.id, Study.short_name)
            .outerjoin(StudyReport, StudyReport.study_id == Study.id)
            .outerjoin(Report, Report.id == StudyReport.report_id)
            .outerjoin(ReportAdded, ReportAdded.report_id == StudyReport.report_id)
            .outerjoin(StudyIntervention, StudyIntervention.study_id == Study.id)
            .outerjoin(Intervention, Intervention.id == StudyIntervention.intervention_id)
            .where(
                Study.short_name.ilike(pattern)
                | Study.trial_registration_id.ilike(pattern)
                | Report.authors.ilike(pattern)
                | Report.trial_registration_id.ilike(pattern)
                | ReportAdded.trial_registration_id.ilike(pattern)
                | Intervention.description.ilike(pattern)
            )
            .distinct()
            .order_by(Study.short_name, Study.id)
            .offset(offset)
            .limit(limit + 1)
        )
        rows = (await self.db.execute(id_stmt)).all()

        has_more = len(rows) > limit
        study_ids = [study_id for study_id, _short_name in rows[:limit]]
        if not study_ids:
            return [], has_more

        studies_by_id = {study.id: study for study in await self.get_studies(study_ids)}
        page = [studies_by_id[study_id] for study_id in study_ids if study_id in studies_by_id]
        return page, has_more

    async def search_studies_advanced(self, query: QueryNode, limit: int, offset: int) -> Tuple[List[Study], bool]:
        """Boolean AND/OR search across studies by field==value comparisons (see
        src/utils/query_parser.py for the grammar and QueryNode shape). Supported fields:
        name/shortName, trialId, author, status, country/countries, intervention,
        condition, outcome, participant, design - each translated into an ilike match,
        an EXISTS against its join table for the many-to-many aspect fields. Same
        two-phase id-then-hydrate paging convention as search_studies() above.
        """
        condition = _query_node_to_condition(query)
        id_stmt = (
            select(Study.id, Study.short_name)
            .where(condition)
            .distinct()
            .order_by(Study.short_name, Study.id)
            .offset(offset)
            .limit(limit + 1)
        )
        rows = (await self.db.execute(id_stmt)).all()

        has_more = len(rows) > limit
        study_ids = [study_id for study_id, _short_name in rows[:limit]]
        if not study_ids:
            return [], has_more

        studies_by_id = {study.id: study for study in await self.get_studies(study_ids)}
        page = [studies_by_id[study_id] for study_id in study_ids if study_id in studies_by_id]
        return page, has_more

    async def get_studies(self, study_ids: Optional[List[int]] = None) -> List[Study]:
        stmt = select(Study)
        if study_ids:
            stmt = stmt.where(Study.id.in_(study_ids))
        result = (await self.db.execute(stmt)).scalars().all()

        #await asyncio.gather(*[log_event(-1, Event(event_type=f"study::{study_id}::visited", timestamp=datetime.now(timezone.utc).isoformat()), self.user_id) for study_id in study_ids])
        return result

    async def get_study_by_id(self, study_id: int) -> Study:
        return await self.db.get(Study, study_id)

    async def search_study_by_shortname(self, shortname: str, cutoff: Optional[str] = None) -> Study:
        stmt = select(Study).where(Study.short_name.ilike(f"%{shortname}%"))
        if cutoff:
            stmt = stmt.where(Study.date_entered < cutoff)
        result = (await self.db.execute(stmt)).scalar_one_or_none()
        return result

    async def get_study_reports_by_study_ids(self, study_ids: Optional[List[int]], cutoff: Optional[str] = None) -> Dict[int, List[Report]]:
        stmt = (
            select(StudyReport.study_id, Report)
            .join(Report, Report.id == StudyReport.report_id)
        )

        if study_ids:
            stmt = stmt.where(StudyReport.study_id.in_(study_ids))

        if cutoff:
            stmt = stmt.where(Report.date_entered < cutoff)

        rows = (await self.db.execute(stmt)).all()

        grouped = {}
        for study_id, report in rows:
            grouped.setdefault(study_id, []).append(report)
        return grouped

    async def get_study_reports_by_study_id(self, study_id: int, cutoff: Optional[str] = None) -> List[Report]:
        result = await self.get_study_reports_by_study_ids(study_ids=[study_id], cutoff=cutoff)
        return result.get(study_id, [])

    async def get_study_reports_by_study_id_page(self, study_id: int, limit: int, offset: int, cutoff: Optional[str] = None) -> Tuple[List[Report], bool]:
        """Paginated version of get_study_reports_by_study_id() above - one extra row
        beyond the page is fetched so has_more can be determined without a separate
        count query, same convention as search_studies()."""
        stmt = (
            select(Report)
            .join(StudyReport, StudyReport.report_id == Report.id)
            .where(StudyReport.study_id == study_id)
        )

        if cutoff:
            stmt = stmt.where(Report.date_entered < cutoff)

        stmt = stmt.order_by(Report.id).offset(offset).limit(limit + 1)

        reports = (await self.db.execute(stmt)).scalars().all()
        has_more = len(reports) > limit
        return reports[:limit], has_more

    async def get_study_persons(self, study_ids: Optional[List[int]] = None, cutoff: Optional[str] = None, normalize_names: bool = True) -> Dict[int, List[str]]:
        stmt = (
            select(StudyReport.study_id.label("study_id"), Report.authors)
            .join(Report, Report.id == StudyReport.report_id)
        )

        if cutoff:
            stmt = stmt.where(Report.date_entered < cutoff)

        if study_ids is not None:
            stmt = stmt.where(StudyReport.study_id.in_(study_ids))

        rows = (await self.db.execute(stmt)).all()

        final_result = {}

        for item in rows:
            key = item[0]
            value = item[1]
            authors = [author.strip() for author in value.split("//")]
            if normalize_names:
                authors = normalize_author_names(authors=authors)

            current_authors = final_result.get(key, [])
            final_result[key] = current_authors + authors

        return final_result

    async def get_study_persons_single(self, study_id : int, cutoff: Optional[str] = None, normalize_names: bool = True) -> List[str]:
        result = await self.get_study_persons(study_ids=[study_id], cutoff=cutoff, normalize_names=normalize_names)
        if study_id in result:
            return result[study_id]
        return []


    async def get_study_date_by_id(self, study_id: int) -> str:
        stmt = select(Study.date_entered).where(Study.id == study_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # Study Aspects

    async def _get_study_aspect(self, stmt) -> Dict[int, List[Tag]]:
        rows = (await self.db.execute(stmt)).all()  # -> [(StudyID, ID, Description), ...]

        # --- Group results by StudyID ---
        final_result: Dict[int, List[Tag]] = {}
        for study_id, aspect_id, description in rows:
            item = Tag(id=str(aspect_id), keyword=description or "")
            final_result.setdefault(study_id, []).append(item)

        return final_result

    async def _get_study_aspect_page(self, stmt, limit: int, offset: int) -> Tuple[List[Tag], bool]:
        """Paginated counterpart of _get_study_aspect() above, for a single study - stmt
        must already be scoped to one study_id and select (id, description) columns in
        a stable order. One extra row beyond the page is fetched so has_more can be
        determined without a separate count query, same convention as
        get_study_reports_by_study_id_page()/search_studies(). Returns Tag directly
        (rather than _get_study_aspect()'s raw {"ID", "Description"} dicts) since every
        caller of the *_single_page() methods below wants a Tag anyway - no reason to
        make them convert a second intermediate shape themselves."""
        rows = (await self.db.execute(stmt.offset(offset).limit(limit + 1))).all()  # -> [(ID, Description), ...]
        has_more = len(rows) > limit
        items = [Tag(id=str(aspect_id), keyword=description or "") for aspect_id, description in rows[:limit]]
        return items, has_more

    async def get_study_interventions(self, study_ids: List[int]) -> Dict[int, List[Tag]]:
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyIntervention.study_id.label("study_id"),
                StudyIntervention.intervention_id.label("id"),
                Intervention.description.label("description"),
            )
            .join(Intervention, Intervention.id == StudyIntervention.intervention_id)
            .where(StudyIntervention.study_id.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_interventions_single(self, study_id : int) -> List[Tag]:
        result = await self.get_study_interventions(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []

    async def get_study_interventions_single_page(self, study_id: int, limit: int, offset: int) -> Tuple[List[Tag], bool]:
        stmt = (
            select(
                StudyIntervention.intervention_id.label("id"),
                Intervention.description.label("description"),
            )
            .join(Intervention, Intervention.id == StudyIntervention.intervention_id)
            .where(StudyIntervention.study_id == study_id)
            .order_by(StudyIntervention.intervention_id)
        )
        return await self._get_study_aspect_page(stmt, limit, offset)

    async def get_study_conditions(self, study_ids: List[int]) -> Dict[int, List[Tag]]:
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyCondition.study_id.label("study_id"),
                StudyCondition.condition_id.label("id"),
                Condition.description.label("description"),
            )
            .join(Condition, Condition.id == StudyCondition.condition_id)
            .where(StudyCondition.study_id.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_conditions_single(self, study_id : int) -> List[Tag]:
        result = await self.get_study_conditions(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []

    async def get_study_conditions_single_page(self, study_id: int, limit: int, offset: int) -> Tuple[List[Tag], bool]:
        stmt = (
            select(
                StudyCondition.condition_id.label("id"),
                Condition.description.label("description"),
            )
            .join(Condition, Condition.id == StudyCondition.condition_id)
            .where(StudyCondition.study_id == study_id)
            .order_by(StudyCondition.condition_id)
        )
        return await self._get_study_aspect_page(stmt, limit, offset)

    async def get_study_outcomes(self, study_ids: List[int]) -> Dict[int, List[Tag]]:
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyOutcome.study_id.label("study_id"),
                StudyOutcome.outcome_id.label("id"),
                Outcome.description.label("description"),
            )
            .join(Outcome, Outcome.id == StudyOutcome.outcome_id)
            .where(StudyOutcome.study_id.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_outcomes_single(self, study_id : int) -> List[Tag]:
        result =await self.get_study_outcomes(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []

    async def get_study_outcomes_single_page(self, study_id: int, limit: int, offset: int) -> Tuple[List[Tag], bool]:
        stmt = (
            select(
                StudyOutcome.outcome_id.label("id"),
                Outcome.description.label("description"),
            )
            .join(Outcome, Outcome.id == StudyOutcome.outcome_id)
            .where(StudyOutcome.study_id == study_id)
            .order_by(StudyOutcome.outcome_id)
        )
        return await self._get_study_aspect_page(stmt, limit, offset)

    async def get_study_participants(self, study_ids: List[int]) -> Dict[int, List[Tag]]:
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyParticipant.study_id.label("study_id"),
                StudyParticipant.participant_id.label("id"),
                Participant.description.label("description"),
                )
            .join(Participant, Participant.id == StudyParticipant.participant_id)
            .where(StudyParticipant.study_id.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_participants_single(self, study_id: int) -> List[Tag]:
        result = await self.get_study_participants(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []

    async def get_study_participants_single_page(self, study_id: int, limit: int, offset: int) -> Tuple[List[Tag], bool]:
        stmt = (
            select(
                StudyParticipant.participant_id.label("id"),
                Participant.description.label("description"),
            )
            .join(Participant, Participant.id == StudyParticipant.participant_id)
            .where(StudyParticipant.study_id == study_id)
            .order_by(StudyParticipant.participant_id)
        )
        return await self._get_study_aspect_page(stmt, limit, offset)

    async def get_study_design(self, study_ids: List[int]) -> Dict[int, List[Tag]]:
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyDesign.study_id.label("study_id"),
                StudyDesign.design_id.label("id"),
                Design.description.label("description"),
                )
            .join(Design, Design.id == StudyDesign.design_id)
            .where(StudyDesign.study_id.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_design_single(self, study_id : int) -> List[Tag]:
        result = await self.get_study_design(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []

    async def get_study_design_single_page(self, study_id: int, limit: int, offset: int) -> Tuple[List[Tag], bool]:
        stmt = (
            select(
                StudyDesign.design_id.label("id"),
                Design.description.label("description"),
            )
            .join(Design, Design.id == StudyDesign.design_id)
            .where(StudyDesign.study_id == study_id)
            .order_by(StudyDesign.design_id)
        )
        return await self._get_study_aspect_page(stmt, limit, offset)

    async def get_all_studies_connected_to_trial_id(self):
        # Define the reusable regex pattern block for PostgreSQL (~ operator)
        regex_conditions = [
            "{col} ~ 'ISRCTN[0-9]{{8}}'",
            "{col} ~ 'ChiCTR[0-9]{{10}}'",
            "{col} ~ 'ChiCTR\\.TRC\\.[0-9]{{8}}'",
            "{col} ~ 'ChiCTR\\.IOR\\.[0-9]{{8}}'",
            "{col} ~ 'ChiCTR-(INR|IPR|POC|IIR|IOQ|OPC)-[0-9]{{8}}'",
            "{col} ~ 'ACTR(N|[0-9])[0-9]{{14}}'",
            "{col} ~ 'CTRI(/|-)[0-9]{{4}}(/|-)[0-9]{{2,3}}(/|-)[0-9]{{6}}'",
            "{col} ~ 'NCT[0-9]{{8}}'",
            "{col} ~ 'DRKS[0-9]{{8}}'",
            "{col} ~ 'NL-OMON[0-9]{{5}}'",
            "{col} ~ 'NL[0-9]{{4}}'",
            "{col} ~ 'IRCT[0-9]{{11,13}}N[0-9]+'",
            "{col} ~ 'KCT[0-9]{{7}}'",
            "{col} ~ 'TCTR[0-9]{{11}}'",
            "{col} ~ 'RBR-.{{7}}'",
            "{col} ~ 'CTIS[0-9]{{4}}-[0-9]{{6}}-[0-9]{{2}}-[0-9]{{2}}'",
            "{col} ~ '(JPRN-)?UMIN[0-9]{{9}}'",
            "{col} ~ '(JPRN-)?JapicCTI-[0-9]{{6}}'",
            "{col} ~ 'JPRN-jRCTs?[0-9]{{9,10}}'",
            "{col} ~ 'EUCTR[0-9]{{4}}-[0-9]{{6}}-[0-9]{{2}}'",
            "{col} ~ 'ITMCTR[0-9]{{10}}'",
            "{col} ~ 'PACTR[0-9]{{15}}'",
            "{col} ~ 'NTR[0-9]{{4,5}}'",
            "{col} ~ 'UKCRNID[0-9]{{4,5}}'",
            "{col} ~ 'SLCTR-[0-9]{{4}}-[0-9]{{3}}'",
            "{col} ~ 'HKCTR-[0-9]{{4}}'",
            "{col} ~ 'M[0-9]{{2}}-[0-9]{{3}}'",
            "{col} ~ 'MCT-[0-9]{{5}}'",
        ]

        def build_regex_block(col):
            return " OR ".join([cond.format(col=col) for cond in regex_conditions])

        # --- Query 1: studies with trial IDs in short_name ---
        query_studies = text(f"""
            SELECT "id"
            FROM "study"
            WHERE {build_regex_block('"short_name"')}
        """)
        result_studies = (await self.db.execute(query_studies)).fetchall()
        all_studies = [row[0] for row in result_studies]

        # --- Query 2: reports with single-trial studies in authors field ---
        query_reports = text(f"""
            SELECT sr."study_id"
            FROM "report" r
            JOIN "study_report" sr ON r."id" = sr."report_id"
            WHERE r."authors" NOT LIKE '%//%'
            AND sr."report_id" IN (
                SELECT "report_id"
                FROM "study_report"
                GROUP BY "report_id"
                HAVING COUNT(DISTINCT "study_id") = 1
            )
            AND {build_regex_block('r."authors"')}
        """)
        result_reports = (await self.db.execute(query_reports)).fetchall()
        all_reports = [row[0] for row in result_reports]

        return all_studies + all_reports

    async def get_study_acronyms(self) -> List[str]:
        stmt = select(Study.short_name)
        rows = (await self.db.execute(stmt)).all()

        acronyms = []
        for (short_name,) in rows:
            # Exclude if more than 2 digits in the short_name
            if len(re.findall(r"\d", short_name)) > 2:
                continue
            acronyms.append(short_name)
        return acronyms
