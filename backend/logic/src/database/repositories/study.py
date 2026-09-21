import os
import re
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlmodel import select, func, text

from dotenv import load_dotenv

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from ..models import Report, Study, StudyAdded, StudyReport
from ..models import StudyIntervention, Intervention, StudyCondition, Condition, StudyOutcome, Outcome, StudyDesign, Design, StudyParticipant, Participant

from ...utils.postprocessing import normalize_author_names

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

class StudyRepository:
    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

    async def commit(self):
        await self.db.commit()

    async def rollback(self):
        await self.db.rollback()

    def process_fields(self, fields):
        if fields is None:
            # Use Report.__table__.columns to dynamically get all field names
            fields = [col.name for col in Report.__table__.columns]
        else:
            # Validate provided field names exist on the Report model
            report_columns = {col.name for col in Report.__table__.columns}
            invalid_fields = [f for f in fields if f not in report_columns]
            if invalid_fields:
                raise ValueError(f"Invalid field(s): {', '.join(invalid_fields)}")
        return tuple(getattr(Report, f) for f in fields), fields

    async def add_study(self, short_name : str, study_status: str, countries : List[str], duration : str, number_of_participants : int, comparison : str) -> Study:
        #TODO add more sophisticated checks
        
        try:
            new_study = Study(
                ShortName=short_name,
                StatusofStudy=study_status,
                Countries="//".join(countries),
                Duration=duration,
                NumberParticipants=str(number_of_participants),
                Comparison=comparison
            )

            self.db.add(new_study)
            await self.db.flush()

            study_added_entry = StudyAdded(
                CRGStudyID=new_study.CRGStudyID,
                CreatedBy=self.user_id,
            )
            self.db.add(study_added_entry)

            await self.db.flush()
            await self.db.refresh(new_study)

            return new_study

        except IntegrityError as e:
            diag = getattr(getattr(e.orig, "__cause__", None), "diag", None)
            if getattr(diag, "constraint_name", None) == "uq_tblstudy_shortname":
                raise DuplicateShortNameError("ShortName already exists")
            raise
    
    async def search_studies(self, trial_ids : Optional[List[str]] = None, number_of_participants : Optional[List[int]] = None, authors : Optional[List[str]] = None):
        study_ids = []
        return await self.get_studies(study_ids=study_ids)

    async def get_studies(self, study_ids: Optional[List[int]] = None) -> List[Study]:
        stmt = select(Study)
        if study_ids:
            stmt = stmt.where(Study.CRGStudyID.in_(study_ids))
        result = (await self.db.execute(stmt)).scalars().all()
        
        #await asyncio.gather(*[log_event(-1, Event(event_type=f"study::{study_id}::visited", timestamp=datetime.now(timezone.utc).isoformat()), self.user_id) for study_id in study_ids])
        return result
    
    async def get_study_by_id(self, study_id: int) -> Study:
        return await self.db.get(Study, study_id)
        
    async def search_study_by_shortname(self, shortname: str, cutoff: Optional[str] = None) -> Study:
        stmt = select(Study).where(Study.ShortName.ilike(f"%{shortname}%"))
        if cutoff:
            stmt = stmt.where(Study.DateEntered < cutoff)
        result = (await self.db.execute(stmt)).scalar_one_or_none()
        return result
    
    async def get_study_reports_by_study_ids(self, study_ids: Optional[List[int]], cutoff: Optional[str] = None, fields: Optional[List[str]] = None) -> Dict[int, List[Report]]:
        select_fields, field_names = self.process_fields(fields)

        stmt = (
            select(StudyReport.CRGStudyID, *select_fields)
            .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
        )

        if study_ids:
            stmt = stmt.where(StudyReport.CRGStudyID.in_(study_ids))

        if cutoff:
            stmt = stmt.where(Report.Dateentered < cutoff)

        rows = (await self.db.execute(stmt)).all()

        grouped = {}
        for row in rows:
            study_id = row[0]  # first item is StudyID
            report_data = dict(zip(field_names, row[1:]))  # remaining fields as dict
            grouped.setdefault(study_id, []).append(report_data)
        return grouped

    async def get_study_reports_by_study_id(self, study_id: int, cutoff=None,) -> List[Report]:
        result = await self.get_study_reports_by_study_ids(study_ids=[study_id], cutoff=cutoff, fields=None,)
        if study_id in result:
            return result[study_id]
        return []
    
    async def get_study_persons(self, study_ids: Optional[List[int]] = None, cutoff: Optional[str] = None, normalize_names: bool = True) -> Dict[int, List[str]]:
        stmt = (
            select(StudyReport.CRGStudyID.label("StudyID"), Report.Authors)
            .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
        )

        if cutoff:
            stmt = stmt.where(Report.Dateentered < cutoff)

        if study_ids is not None:
            stmt = stmt.where(StudyReport.CRGStudyID.in_(study_ids))

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
    
    async def get_study_id_by_trial_ids(self, trial_ids: List[str], cutoff: Optional[str] = None) -> Dict[str, List[int]]:
        trial_ids_norm = [trial_id.replace("/", "-") for trial_id in trial_ids]
        result_map = {}

        for orig_trial_id, trial_id in zip(trial_ids, trial_ids_norm):
            alternative_ids = [trial_id]
            if trial_id in trial_id_mapping.keys():
                alternative_ids.extend(trial_id_mapping[trial_id])
            alternative_ids = [current_id.replace("/", "-") for current_id in alternative_ids]

            # Build dynamic LIKE conditions for Authors
            authors_filter = func.replace(Report.Authors, "/", "-").like(f"%{alternative_ids[0]}%")
            for current_id in alternative_ids[1:]:
                authors_filter = authors_filter | func.replace(Report.Authors, "/", "-").like(f"%{current_id}%")

            trial_filter = func.replace(Report.TrialRegistrationID, "/", "-").in_(alternative_ids)

            stmt_study = select(Study.CRGStudyID, text("'study' as source")).where(
                (Study.ShortName.in_(alternative_ids)) |
                (Study.TrialRegistrationID.in_(alternative_ids))
            )

            stmt_reports = (
                select(StudyReport.CRGStudyID, text("'report' as source"))
                .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
                .where(authors_filter | trial_filter)
            )

            if cutoff is not None:
                stmt_study = stmt_study.where(Study.DateEntered < cutoff)
                stmt_reports = stmt_reports.where(Report.Dateentered < cutoff)

            combined_stmt = stmt_study.union_all(stmt_reports)
            rows = (await self.db.execute(combined_stmt)).all()  # [(CRGStudyID, source), ...]

            # Sort: 'study' source first, then 'report'
            sorted_rows = sorted(rows, key=lambda x: 0 if x[1] == 'study' else 1)

            # Remove duplicates, preserving order (study > report)
            seen = set()
            ordered_ids = []
            for study_id, _ in sorted_rows:
                if study_id not in seen:
                    seen.add(study_id)
                    ordered_ids.append(study_id)
            result_map[orig_trial_id] = ordered_ids

        return result_map

    async def get_study_id_by_trial_id(self, trial_id: str, cutoff: Optional[str] = None) -> List[int]:
        result = (await self.get_study_id_by_trial_ids([trial_id],cutoff))
        if trial_id in result:
            return result[trial_id]
        return None

    async def get_study_date_by_id(self, study_id: int) -> str:
        stmt = select(Study.DateEntered).where(Study.CRGStudyID == study_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()
    
    # Study Aspects
    
    async def _get_study_aspect(self, stmt):
        rows = (await self.db.execute(stmt)).all()  # -> [(StudyID, ID, Description), ...]

        # --- Group results by StudyID ---
        final_result: Dict[int, List[Dict[str, Any]]] = {}
        for study_id, intervention_id, description in rows:
            item = {"ID": intervention_id, "Description": description}
            final_result.setdefault(study_id, []).append(item)

        return final_result
    
    async def get_study_interventions(self, study_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyIntervention.CRGStudyID.label("StudyID"),
                StudyIntervention.InterventionID.label("ID"),
                Intervention.InterventionDescription.label("Description"),
            )
            .join(Intervention, Intervention.InterventionID == StudyIntervention.InterventionID)
            .where(StudyIntervention.CRGStudyID.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_interventions_single(self, study_id : int) -> List[Dict[str, Any]]:
        result = await self.get_study_interventions(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []
    
    async def get_study_conditions(self, study_ids: List[int]):
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyCondition.CRGStudyID.label("StudyID"),
                StudyCondition.HealthCareConditionID.label("ID"),
                Condition.HealthCareConditionDescription.label("Description"),
            )
            .join(Condition, Condition.HealthCareConditionID == StudyCondition.HealthCareConditionID)
            .where(StudyCondition.CRGStudyID.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_conditions_single(self, study_id : int) -> List[Dict[str, Any]]:
        result = await self.get_study_conditions(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []
    
    async def get_study_outcomes(self, study_ids: List[int]):
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyOutcome.CRGStudyID.label("StudyID"),
                StudyOutcome.OutcomeID.label("ID"),
                Outcome.OutcomeDescription.label("Description"),
            )
            .join(Outcome, Outcome.OutcomeID == StudyOutcome.OutcomeID)
            .where(StudyOutcome.CRGStudyID.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_outcomes_single(self, study_id : int) -> List[Dict[str, Any]]:
        result =await self.get_study_outcomes(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []

    async def get_study_participants(self, study_ids: List[int]) -> Dict[int, List[str]]:
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyParticipant.CRGStudyID.label("StudyID"),
                StudyParticipant.ParticipantsID.label("ID"),
                Participant.ParticipantDescription.label("Description"),
                )
            .join(Participant, Participant.ParticipantsID == StudyParticipant.ParticipantsID)
            .where(StudyParticipant.CRGStudyID.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_participants_single(self, study_id: int) -> List[str]:
        result = await self.get_study_participants(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []
    
    async def get_study_design(self, study_ids: List[int]) -> Dict[int, List[str]]:
        if not study_ids:
            return {}
        stmt = (
            select(
                StudyDesign.CRGStudyID.label("StudyID"),
                StudyDesign.DesignID.label("ID"),
                Design.DesignDescription.label("Description"),
                )
            .join(Design, Design.DesignID == StudyDesign.DesignID)
            .where(StudyDesign.CRGStudyID.in_(study_ids))
        )

        return await self._get_study_aspect(stmt)

    async def get_study_design_single(self, study_id : int) -> List[str]:
        result = await self.get_study_design(study_ids=[study_id])
        if study_id in result.keys():
            return result[study_id]
        return []
    
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

        # --- Query 1: studies with trial IDs in ShortName ---
        query_studies = text(f"""
            SELECT "CRGStudyID"
            FROM "tblStudy"
            WHERE {build_regex_block('"ShortName"')}
        """)
        result_studies = (await self.db.execute(query_studies)).fetchall()
        all_studies = [row[0] for row in result_studies]

        # --- Query 2: reports with single-trial studies in Authors field ---
        query_reports = text(f"""
            SELECT sr."CRGStudyID"
            FROM "tblReport" r
            JOIN "tblStudyReport" sr ON r."CRGReportID" = sr."CRGReportID"
            WHERE r."Authors" NOT LIKE '%//%'
            AND sr."CRGReportID" IN (
                SELECT "CRGReportID"
                FROM "tblStudyReport"
                GROUP BY "CRGReportID"
                HAVING COUNT(DISTINCT "CRGStudyID") = 1
            )
            AND {build_regex_block('r."Authors"')}
        """)
        result_reports = (await self.db.execute(query_reports)).fetchall()
        all_reports = [row[0] for row in result_reports]

        return all_studies + all_reports
    
    async def get_study_acronyms(self) -> List[str]:
        stmt = select(Study.ShortName)
        rows = (await self.db.execute(stmt)).all()

        acronyms = []
        for (short_name,) in rows:
            # Exclude if more than 2 digits in the ShortName
            if len(re.findall(r"\d", short_name)) > 2:
                continue
            acronyms.append(short_name)
        return acronyms