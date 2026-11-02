"""The records of trial registrations read from their primary registers. A register's own record is fuller than the
WHO ICTRP copy of it (e.g. the arms of a ClinicalTrials.gov study and the interventions each one receives); a trial of
any other register, or one its register can't serve, falls back to the WHO record (see CrawlerService)."""

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Tuple

import httpx

from ..utils.trial_registration_id import isrctn, nct, nlomon


@dataclass
class RegistryRecord:
    """A registry record as titled sections of label/value rows, rendered as the HTML of the record's PDF."""

    register: str
    url: str
    sections: List[Tuple[str, List[Tuple[str, str]]]] = field(default_factory=list)

    def add(self, heading: str, rows: Iterable[Tuple[str, Any]]) -> None:
        """A section of the rows that have a value; a section without any is left out."""
        kept = [(label, self._text(value)) for label, value in rows]
        kept = [(label, value) for label, value in kept if value]
        if kept:
            self.sections.append((heading, kept))

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return "\n".join(dict.fromkeys(t for t in (RegistryRecord._text(v) for v in value) if t))
        return str(value).strip()

    def to_markdown(self) -> str:
        """The record as the fulltext of its report: one heading per section, one paragraph per row (a value of
        several lines starts on the line after its label)."""
        parts = [f"Register: {self.register}\n\nURL: {self.url}"]
        for heading, rows in self.sections:
            parts.append(f"## {heading}")
            parts += [f"{label}{chr(10) if chr(10) in value else ' '}{value}" for label, value in rows]
        return "\n\n".join(parts)

    def to_html(self) -> str:
        def cell(text: str) -> str:
            return html.escape(text).replace("\n", "<br>")

        parts = [f"<table><tr><td>Register:</td><td>{cell(self.register)}</td></tr>"
                 f"<tr><td>URL:</td><td>{cell(self.url)}</td></tr></table>"]
        for heading, rows in self.sections:
            body = "".join(f"<tr><td>{cell(label)}</td><td>{cell(value)}</td></tr>" for label, value in rows)
            parts.append(f"<h2>{cell(heading)}</h2><table>{body}</table>")
        return "\n".join(parts)


class TrialRegistry:
    """A primary register that serves the records of its trial ids."""

    TIMEOUT = 30

    def matches(self, trial_id: str) -> bool:
        raise NotImplementedError

    async def get_record(self, trial_id: str) -> RegistryRecord:
        """The record of `trial_id`; raises if the register doesn't have it or can't be reached."""
        raise NotImplementedError

    async def _get(self, url: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Accept": "application/json, application/xml"})
            resp.raise_for_status()
            return resp


class ClinicalTrialsGovRegistry(TrialRegistry):
    """ClinicalTrials.gov through its public API (https://clinicaltrials.gov/data-api/api)."""

    API = "https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    STUDY = "https://clinicaltrials.gov/study/{nct_id}"

    def matches(self, trial_id: str) -> bool:
        return nct.fullmatch(trial_id) is not None

    @staticmethod
    def _nct_id(trial_id: str) -> str:
        return "NCT" + re.sub(r"\D", "", trial_id)

    @classmethod
    def _unescape(cls, value: Any) -> Any:
        """The texts of the API without their markdown escapes ("\\>= 18 years" is ">= 18 years"), so that the PDF
        and the fulltext written from the record read the same."""
        if isinstance(value, str):
            return re.sub(r"\\([\\`*_{}\[\]()#+\-.!<>|^=~])", r"\1", value)
        if isinstance(value, list):
            return [cls._unescape(v) for v in value]
        if isinstance(value, dict):
            return {k: cls._unescape(v) for k, v in value.items()}
        return value

    @staticmethod
    def _label(code: Optional[str]) -> str:
        """An enum of the API as words ("ACTIVE_COMPARATOR" is "Active comparator")."""
        return (code or "").replace("_", " ").capitalize()

    async def get_record(self, trial_id: str) -> RegistryRecord:
        nct_id = self._nct_id(trial_id)
        study = self._unescape((await self._get(self.API.format(nct_id=nct_id))).json()["protocolSection"])
        ident, status = study.get("identificationModule", {}), study.get("statusModule", {})
        design, arms = study.get("designModule", {}), study.get("armsInterventionsModule", {})
        record = RegistryRecord("ClinicalTrials.gov", self.STUDY.format(nct_id=nct_id))

        record.add("Identification", [
            ("Main ID:", ident.get("nctId")),
            ("Secondary ID(s):", [ident.get("orgStudyIdInfo", {}).get("id")] + [i.get("id") for i in ident.get("secondaryIdInfos", [])]),
            ("Acronym:", ident.get("acronym")),
            ("Public title:", ident.get("briefTitle")),
            ("Scientific title:", ident.get("officialTitle")),
            ("Primary sponsor:", study.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name")),
            ("Recruitment status:", self._label(status.get("overallStatus"))),
            ("Date of first enrolment:", status.get("startDateStruct", {}).get("date")),
            ("Date of completion:", status.get("completionDateStruct", {}).get("date")),
        ])
        description = study.get("descriptionModule", {})
        record.add("Summary", [
            ("Brief summary:", description.get("briefSummary")),
            ("Detailed description:", description.get("detailedDescription")),
        ])
        conditions = study.get("conditionsModule", {})
        record.add("Health Condition(s) or Problem(s) studied", [
            ("Conditions:", conditions.get("conditions")),
            ("Keywords:", ", ".join(conditions.get("keywords", []))),
        ])
        info, enrollment = design.get("designInfo", {}), design.get("enrollmentInfo", {})
        record.add("Study design", [
            ("Study type:", self._label(design.get("studyType"))),
            ("Phase:", ", ".join(self._label(p) for p in design.get("phases", []))),
            ("Allocation:", self._label(info.get("allocation"))),
            ("Intervention model:", self._label(info.get("interventionModel"))),
            ("Primary purpose:", self._label(info.get("primaryPurpose"))),
            ("Masking:", self._label(info.get("maskingInfo", {}).get("masking"))),
            ("Target sample size:", f"{enrollment['count']} ({self._label(enrollment.get('type'))})" if "count" in enrollment else None),
        ])
        for arm in arms.get("armGroups", []):
            record.add(f"Arm: {arm.get('label', '')}", [
                ("Arm type:", self._label(arm.get("type"))),
                ("Interventions:", arm.get("interventionNames")),
                ("Description:", arm.get("description")),
            ])
        record.add("Intervention(s)", [
            (f"{self._label(i.get('type'))}: {i.get('name', '')}",
             "\n".join(filter(None, [i.get("description"), "Other names: " + ", ".join(i["otherNames"]) if i.get("otherNames") else None])))
            for i in arms.get("interventions", [])
        ])
        outcomes = study.get("outcomesModule", {})
        for heading, key in (("Primary Outcome(s)", "primaryOutcomes"), ("Secondary Outcome(s)", "secondaryOutcomes"), ("Other Outcome(s)", "otherOutcomes")):
            record.add(heading, [
                (o.get("measure", ""), "\n".join(filter(None, [f"[Time Frame: {o['timeFrame']}]" if o.get("timeFrame") else None, o.get("description")])))
                for o in outcomes.get(key, [])
            ])
        eligibility = study.get("eligibilityModule", {})
        record.add("Key inclusion & exclusion criteria", [
            ("Criteria:", eligibility.get("eligibilityCriteria")),
            ("Gender:", self._label(eligibility.get("sex"))),
            ("Age minimum:", eligibility.get("minimumAge")),
            ("Age maximum:", eligibility.get("maximumAge")),
            ("Healthy volunteers:", {True: "Yes", False: "No"}.get(eligibility.get("healthyVolunteers"))),
        ])
        locations = study.get("contactsLocationsModule", {}).get("locations", [])
        record.add("Countries of recruitment", [("Countries:", list(dict.fromkeys(l["country"] for l in locations if l.get("country"))))])
        return record


class IsrctnRegistry(TrialRegistry):
    """The ISRCTN registry through its public API."""

    API = "https://www.isrctn.com/api/trial/{isrctn_id}/format/default"
    STUDY = "https://www.isrctn.com/{isrctn_id}"
    NS = {"i": "http://www.67bricks.com/isrctn"}

    def matches(self, trial_id: str) -> bool:
        return isrctn.fullmatch(trial_id) is not None

    async def get_record(self, trial_id: str) -> RegistryRecord:
        isrctn_id = trial_id.upper()
        root = ET.fromstring((await self._get(self.API.format(isrctn_id=isrctn_id))).content)
        trial = root.find("i:trial", self.NS)
        if trial is None:
            raise ValueError(f"ISRCTN has no trial {isrctn_id}")

        def text(path: str) -> Optional[str]:
            return trial.findtext(path, namespaces=self.NS)

        def texts(path: str) -> List[str]:
            return [e.text.strip() for e in trial.findall(path, self.NS) if e.text and e.text.strip()]

        record = RegistryRecord("ISRCTN", self.STUDY.format(isrctn_id=isrctn_id))
        record.add("Identification", [
            ("Main ID:", isrctn_id),
            ("Secondary ID(s):", texts("i:externalRefs/i:secondaryNumbers/i:secondaryNumber")
                + [f"EudraCT {n}" for n in texts("i:externalRefs/i:eudraCTNumber")]
                + [f"IRAS {n}" for n in texts("i:externalRefs/i:irasNumber")]
                + texts("i:externalRefs/i:protocolSerialNumber")),
            ("Acronym:", text("i:trialDescription/i:acronym")),
            ("Public title:", text("i:trialDescription/i:title")),
            ("Scientific title:", text("i:trialDescription/i:scientificTitle")),
            ("Primary sponsor:", root.findtext("i:sponsor/i:organisation", namespaces=self.NS)),
            ("Source(s) of monetary support:", [e.text for e in root.findall("i:funder/i:name", self.NS)]),
            ("Date of first enrolment:", (text("i:participants/i:recruitmentStart") or "")[:10]),
            ("Date of completion:", (text("i:participants/i:recruitmentEnd") or "")[:10]),
        ])
        record.add("Summary", [
            ("Plain English summary:", text("i:trialDescription/i:plainEnglishSummary")),
            ("Study hypothesis:", text("i:trialDescription/i:studyHypothesis")),
        ])
        record.add("Health Condition(s) or Problem(s) studied", [
            ("Condition:", texts("i:conditions/i:condition/i:description")),
            ("Disease class:", texts("i:conditions/i:condition/i:diseaseClass1")),
        ])
        record.add("Study design", [
            ("Study design:", text("i:trialDesign/i:studyDesign")),
            ("Study type:", text("i:trialDesign/i:primaryStudyDesign")),
            ("Secondary study design:", text("i:trialDesign/i:secondaryStudyDesign")),
            ("Trial type:", texts("i:trialDesign/i:trialTypes/i:trialType")),
            ("Phase:", texts("i:interventions/i:intervention/i:phase")),
        ])
        for number, intervention in enumerate(trial.findall("i:interventions/i:intervention", self.NS), start=1):
            record.add("Intervention(s)" if number == 1 else f"Intervention(s) {number}", [
                ("Intervention type:", intervention.findtext("i:interventionType", namespaces=self.NS)),
                ("Drug names:", intervention.findtext("i:drugNames", namespaces=self.NS)),
                ("Description:", intervention.findtext("i:description", namespaces=self.NS)),
            ])
        record.add("Primary Outcome(s)", [("Primary outcome measure:", texts("i:trialDescription/i:primaryOutcome"))])
        record.add("Secondary Outcome(s)", [("Secondary outcome measures:", texts("i:trialDescription/i:secondaryOutcome"))])
        record.add("Participants", [
            ("Participant type:", texts("i:participants/i:participantTypes/i:participantType")),
            ("Age group:", text("i:participants/i:ageRange")),
            ("Gender:", text("i:participants/i:gender")),
            ("Target sample size:", text("i:participants/i:targetEnrolment")),
            ("Total final enrolment:", text("i:participants/i:totalFinalEnrolment")),
            ("Inclusion criteria:", text("i:participants/i:inclusion")),
            ("Exclusion criteria:", text("i:participants/i:exclusion")),
        ])
        record.add("Countries of recruitment", [("Countries:", texts("i:participants/i:recruitmentCountries/i:country"))])
        return record


class OmonRegistry(TrialRegistry):
    """The Dutch register Overview of Medical Research in the Netherlands (OMON) through its public API. An NL-OMON id
    is the OMON trial number; the older NL and NTR numbers are only secondary ids there and stay on the WHO record."""

    API = "https://onderzoekmetmensen.nl/nl/api/v1/trial/{number}"
    STUDY = "https://onderzoekmetmensen.nl/en/trial/{number}"

    def matches(self, trial_id: str) -> bool:
        return nlomon.fullmatch(trial_id) is not None

    @staticmethod
    def _plain(text: Optional[str]) -> str:
        """A value of OMON as text: some are HTML ("<br />", "<p>")."""
        text = re.sub(r"(?i)<br\s*/?>|</p>", "\n", text or "")
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
        return re.sub(r"\n\s*\n+", "\n", text).strip()

    async def get_record(self, trial_id: str) -> RegistryRecord:
        number = re.sub(r"\D", "", trial_id)
        trial = ET.fromstring((await self._get(self.API.format(number=number))).content).find("trial")
        if trial is None:
            raise ValueError(f"OMON has no trial {trial_id}")

        def english(path: str) -> List[ET.Element]:
            """The entries of `path` in English, or in any language if there is no English one."""
            entries = trial.findall(path)
            return [e for e in entries if e.findtext("language") == "EN"] or entries

        def first(path: str, child: str) -> str:
            return next((self._plain(e.findtext(child)) for e in english(path) if (e.findtext(child) or "").strip()), "")

        def every(path: str, child: str) -> List[str]:
            return [self._plain(e.findtext(child)) for e in english(path) if (e.findtext(child) or "").strip()]

        def text(path: str) -> str:
            return self._plain(trial.findtext(path))

        record = RegistryRecord("OMON", self.STUDY.format(number=number))
        record.add("Identification", [
            ("Main ID:", f"NL-OMON{number}"),
            ("Secondary ID(s):", list(dict.fromkeys(
                [e.findtext("sec_id") for e in trial.findall("secondary_ids/secondary_id")] + [text("ccmo_ids/toetsingonline_id")]
            ))),
            ("Acronym:", first("titles/title", "acronym")),
            ("Public title:", first("titles/title", "public_titles")),
            ("Scientific title:", first("titles/title", "scientific_title")),
            ("Source register:", text("main/source")),
            ("Primary sponsor:", text("main/primary_sponsor")),
            ("Source(s) of monetary support:", [self._plain(e.text) for e in trial.findall("source_support/source_name")]),
            ("Date of registration:", text("main/date_registration")),
            ("Date of first enrolment:", text("enrolments/enrolment/date_enrolment")),
            ("Recruitment status:", text("enrolments/enrolment/recruitment_status")),
        ])
        record.add("Summary", [
            ("Background:", first("abstracts/abstract", "background")),
            ("Objective:", first("abstracts/abstract", "objective")),
            ("Study design:", first("abstracts/abstract", "design")),
        ])
        record.add("Health Condition(s) or Problem(s) studied", [
            ("Condition:", text("main/hc_freetext")),
            ("Keywords:", every("health_condition_keywords/healthConditionKeyword", "hc_keyword")),
        ])
        record.add("Study design", [
            ("Study type:", text("main/study_type")),
            ("Phase:", text("main/phase")),
            ("Allocation:", text("main/study_design/allocation")),
            ("Masking:", text("main/study_design/masking")),
            ("Control:", text("main/study_design/control")),
            ("Assignment:", text("main/study_design/assignment")),
            ("Primary purpose:", text("main/study_design/purpose")),
        ])
        record.add("Intervention(s)", [
            ("Intervention:", first("abstracts/abstract", "intervention")),
            ("Intervention keywords:", every("intervention_keywords/intervention_keyword", "i_keyword")),
            ("Product type:", every("products/product", "type")),
        ])
        record.add("Primary Outcome(s)", [("Primary outcome:", every("primary_outcomes/primaryOutcome", "prim_outcome"))])
        record.add("Secondary Outcome(s)", [("Secondary outcome:", every("secondary_outcomes/secondaryOutcome", "sec_outcome"))])
        record.add("Participants", [
            ("Age group:", [self._plain(e.text) for e in trial.findall("targetAudiences/targetAudience/ageGroup")]),
            ("Target sample size:", text("enrolments/enrolment/target_size")),
            ("Enrolment:", text("enrolments/enrolment/type_enrolment")),
            ("Actual enrolment:", text("trialResult/actual_enrolment")),
            ("Inclusion criteria:", first("criterias/criteria", "inclusion_criteria")),
            ("Exclusion criteria:", first("criterias/criteria", "exclusion_criteria")),
        ])
        record.add("Countries of recruitment", [("Countries:", [self._plain(e.text) for e in trial.findall("countries/country")])])
        return record
