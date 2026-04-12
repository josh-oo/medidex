import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, List, Union, Dict, Optional, Tuple, Literal

from pydantic import BaseModel, Field

from langchain.tools import tool, ToolRuntime

from langchain.messages import SystemMessage
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from ..database import ReportRepository, StudyRepository
from .core import StudySimilaritySearchService
from .report import DocumentService

SYSTEM_MESSAGE_TEXT = """
You are a clinical research assistant tasked with determining whether a new report belongs to an existing candidate study. 
This is necessary since one study sometimes produces multiple scientific reports or articles which then need to be mapped back to the study they belong to.
Please look at common signals such as trial registration ID, number of participants, interventions and the countries mentioned.
You will get the title, abstract and authors for the corresponding new report. 
If you need more information you can use a tool to retrieve the full text of the current report.
Please use the available tools to retrieve candidate studies.
The workflow should look like:
1. retrieve the next likely study candidate. The most likely candidate (cosine similarity retrieval based on title and abstract) is returned when calling the tool for the first time, the second time the second most likely candidate is returned and so on ...
   For each candidate you will retrieve metadata like 'number of participants' if you need further information you can use the corresponding tools to retrieve more detailed information.
2. considering all the signals and compare them to the candidate study information (metadata / assigned reports) in order to decide if the current report belongs to this study
    if you are unsure you can also load the fulltexts for the reports already assigned to this study using the corresponding tools
    -> if this candidate study is definitely a match (the current report belongs to this study):
    then return the id (int) of this candidate study IMPORTANT: before returning your final result make sure that you checked all relevant information for the chosen candidate study
    -> if this candidate study is not a match (the current report most likely does not belong to this study):
    then proceed with step 1. loading the next likely candidate study.
    -> if you already processed a reasonable number of studies without finding a matching candidate:
    then break the loop by recommending that the user add a new study to their database IMPORTANT: before suggesting a new study make sure that you used all available resources (fulltexts, report lists, ...)
"""

@dataclass
class AgentContext:
    current_report: int
    visited_candidate_studies: int
    study_repo : StudyRepository
    report_repo : ReportRepository
    study_similarity_service : StudySimilaritySearchService
    document_service :  DocumentService

class ExistingStudy(BaseModel):
    reason: str = Field(description="The reason why this study is a match for the input report")
    studyId: int = Field(description="The id of the matching candidate study")

class Comparison(BaseModel):
    intervention: list[str] = Field(description="The list of interventions used in this study. If possible use the database terminology.")
    control: list[str] = Field(description="The list of control methods used in this study. If possible use the database terminology.")

class NewStudySuggestion(BaseModel):
    shortName: str = Field(description="The shortname of the study (use the trial registration id if provided otherwise use first author + year e.g. 'Stanfield 2025').")
    status: Literal[None, "Closed", "Stopped early", "Open/Ongoing", "Planned"] = Field(description="The status of the study if any hints found in the given material.")
    countries: list[str] = Field(description="The countries where the study took place (if available)")
    durationUnit: Literal["hours", "days", "weeks", "months", "years"] = Field(description="The unit of the study duration mentioned. ")
    durationValue: int = Field(description="The value of the study duration mentioned.")
    numberParticipants: int = Field(description="The number of participants in this study.")
    comparison: list[Comparison] = Field(description="The comparison used in this study.")
    trialId: Optional[str] = Field(description="The trial id linked to this study (if mentioned).")

class NewStudy(BaseModel):
    reason: str = Field(description="The reason why you couldn't find an existing study for the input report")
    newStudySuggestion : NewStudySuggestion = Field(description="The attributes for the new study to be entered in the database")

Output = Union[ExistingStudy, NewStudy]

@tool
async def fetch_next_candidate_study(reason: str, runtime: ToolRuntime[AgentContext]) -> Dict[str,str]:  
    """
    Fetch the next (most relevant) candidate study for the current report based on its title / abstract

    Args:
        reason: The reason why you need to visit the next study
    """
    report_id = runtime.context.current_report
    visited_candidate_studies = runtime.context.visited_candidate_studies
    
    response = await runtime.context.study_similarity_service.get_similar_studies_by_id(
        report_id,
        aspect='default',
        cutoff=None,
        negative_reports=None,
        negative_studies=None,
        k=visited_candidate_studies + 1,
        return_details=False
    )

    study_id = response['CRGStudyID'][visited_candidate_studies]

    response = await runtime.context.study_repo.get_study_by_id(study_id=study_id)

    result = {
        "studyId": response.CRGStudyID,
        "shortName": response.ShortName,
        "trialId": response.TrialistContactDetails,
        "numberParticipants": response.NumberParticipants,
        "countries": response.Countries,
        "duration": response.Duration,
        "comparison": response.Comparison,
    }

    runtime.context.visited_candidate_studies += 1
    return result

@tool
async def fetch_report_fulltext(report_id: Optional[int], runtime: ToolRuntime[AgentContext]) -> str:  
    """Fetch the corresponding fulltext for a given report

     Args:
        report_id: The id of the report you want the fulltext for leave it empty (None) to retrieve the current reports fulltext
    """
    if report_id is None:
        return await runtime.context.document_service.get_fulltext(runtime.context.current_report, fast=False)
    return await runtime.context.document_service.get_fulltext(report_id, fast=False)

@tool
async def fetch_report_abstract(report_id: int, runtime: ToolRuntime[AgentContext]) -> str:  
    """Fetch the corresponding abstract for a given report
    
    Args:
        report_id: The id of the report you want the abstract for
    """
    response = await runtime.context.report_repo.get_report_by_id(report_id)
    return response.Abstract

@tool
async def fetch_report_abstract(report_id: int, runtime: ToolRuntime[AgentContext]) -> str:  
    """Fetch the corresponding abstract for a given report
    
    Args:
        report_id: The id of the report you want the abstract for
    """
    response = await runtime.context.report_repo.get_report_by_id(report_id)
    return response.Abstract

@tool
async def fetch_study_reports(study_id : int, runtime: ToolRuntime[AgentContext]) -> List[Dict[str,str]]:  
    """Get all the reports already assigned to the corresponding study

    Args:
        study_id: The id of the study 
    """
    result = []
    response = await runtime.context.study_repo.get_study_reports_by_study_id(study_id)
    for item in response:
        result.append({'reportId': item['CRGReportID'], 'title': item['Title']})
    return result

@tool
async def fetch_study_interventions(study_id : int, runtime: ToolRuntime[AgentContext]) -> List[str]:  
    """Get all the interventions already assigned to the corresponding study

    Args:
        study_id: The id of the study 
    """
    response = await runtime.context.study_repo.get_study_interventions_single(study_id)
    results = []
    for item in response:
        results.append(item['Description'])
    return results

@tool
async def fetch_study_persons(study_id : int, runtime: ToolRuntime[AgentContext]) -> List[str]:
    """Get all persons associated with this study

    Args:
        study_id: The id of the study 
    """
    return await runtime.context.study_repo.get_study_persons_single(study_id)

class AgentService:
    def __init__(
        self,
        report_repo: ReportRepository,
        study_repo : StudyRepository,
        document_service :  DocumentService,
        study_similarity_service: StudySimilaritySearchService,
        model: Any,
    ):
        self.report_repo = report_repo
        self.study_repo = study_repo
        self.study_similarity_service = study_similarity_service
        self.document_service = document_service
        self.model = model

        system_message = SystemMessage(
            content=[
                {
                    "type": "text",
                    "text": SYSTEM_MESSAGE_TEXT,
                }
            ]
        )

        self.agent = create_agent(
            model=self.model,
            tools=[fetch_next_candidate_study, fetch_report_fulltext, fetch_study_reports, fetch_study_interventions, fetch_study_persons, fetch_report_abstract],
            context_schema=AgentContext,
            system_prompt=system_message,
            response_format=ToolStrategy(Output),
        )

    async def _load_report_context(self, report_id : int) -> str:
        report = await self.report_repo.get_report_by_id(report_id)
        if report is None:
            raise ValueError(f"Report {report_id} not found")

        authors = [author.strip() for author in (report.Authors or "").split("//") if author.strip()]
        return (
            f"Title: {report.Title or ''}\n"
            f"Abstract: {report.Abstract or ''}\n"
            f"Authors: {', '.join(authors)}"
        )

    async def ainvoke(self, report_id : int) -> ExistingStudy | NewStudy:
        report_string = await self._load_report_context(report_id)

        result = await self.agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Please find a matching study id or propose a new study creation "
                            f"for the following report\n{report_string}"
                        ),
                    }
                ]
            },
            context=AgentContext(
                current_report=report_id,
                visited_candidate_studies=0,
                study_repo=self.study_repo,
                report_repo=self.report_repo,
                study_similarity_service=self.study_similarity_service,
                document_service=self.document_service,
            ),
        )
        return result['structured_response']

    async def astream(self, report_id : int) -> AsyncGenerator[str, None]:
        """Stream agent execution events as server-sent events.
        
        Yields:
            Server-sent event formatted strings with agent execution updates
        """
        report_string = await self._load_report_context(report_id)

        async for event in self.agent.astream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Please find a matching study id or propose a new study creation "
                            f"for the following report\n{report_string}"
                        ),
                    }
                ]
            },
            context=AgentContext(
                current_report=report_id,
                visited_candidate_studies=0,
                study_repo=self.study_repo,
                report_repo=self.report_repo,
                study_similarity_service=self.study_similarity_service,
                document_service=self.document_service,
            ),
            version="v1",
            stream_mode="updates",
        ):
            final_payload = {}
            payload, structured_output = self.parse_event(event)
            if structured_output is not None:
                final_payload['event'] = "final"
                final_payload['payload'] = structured_output
                yield f"data: {json.dumps(final_payload, ensure_ascii=True)}\n\n"

            else:
                final_payload = {'event': "info", 'payload': payload}
                yield f"data: {json.dumps(final_payload, ensure_ascii=True)}\n\n"

        yield 'data: {"event":"complete"}\n\n'

    def parse_event(self, event) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        payload: List[Dict[str, Any]] = []
        structured_output: Optional[Dict[str, Any]] = None

        if "model" in event.keys():
            for tool_call in event['model']['messages'][0].tool_calls:
                if tool_call['name'] == "fetch_study_interventions":
                    payload.append({'studyId': tool_call["args"]["study_id"], 'message': f"Checking study interventions."})
                elif tool_call['name'] == "fetch_study_reports":
                    payload.append({'studyId': tool_call["args"]["study_id"], 'message': f"Checking study reports."})
                elif tool_call['name'] == "fetch_current_fulltext":
                    payload.append({'studyId': None, 'message': f"Reading report fulltext."})
                elif tool_call['name'] == "ExistingStudy":
                    structured_output = tool_call.get("args")
                    structured_output['type'] = "existing"
                elif tool_call['name'] == "NewStudy":
                    structured_output = tool_call.get("args")
                    structured_output['type'] = "new"
        elif "tools" in event.keys():
            for item in event['tools']['messages']:
                if item.name == "fetch_next_candidate_study":
                    content = json.loads(item.content) if isinstance(item.content, str) else item.content
                    payload.append({'studyId': content["studyId"], 'message': f"Start checking study {content['shortName']}."})
                elif item.name == "ExistingStudy":
                    if isinstance(item.content, str):
                        structured_output = json.loads(item.content)
                    elif isinstance(item.content, dict):
                        structured_output = item.content
                    structured_output['type'] = "existing"
                elif item.name == "NewStudy":
                    if isinstance(item.content, str):
                        structured_output = json.loads(item.content)
                    elif isinstance(item.content, dict):
                        structured_output = item.content
                    structured_output['type'] = "new"

        return payload, structured_output

