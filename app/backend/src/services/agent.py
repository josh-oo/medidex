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
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

SYSTEM_MESSAGE_AUTOBOT = """
You are a clinical research assistant tasked with determining whether a new report belongs to an existing candidate study. 
This is necessary since one study sometimes produces multiple scientific reports or articles which then need to be mapped back to the study they belong to.
Please look at common signals such as trial registration ID, number of participants, interventions and the countries mentioned.
You will get the title, abstract and authors for the corresponding new report. 
If you need more information you can use a tool to retrieve the full text of the current report.
Please use the available tools to retrieve teh most similar candidate studies. If the report is a retraction, corrigendum, or similar notice, consider resolving the reference directly.
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

SYSTEM_MESSAGE_QUESTION_ANSWERING = """
You are a clinical research assistant tasked with answering follow-up questions about report-to-study matching.
Use the available tools to inspect candidate studies, report metadata, and report full text when needed.
Ground your answers in the retrieved evidence and avoid unsupported assumptions.
If information is missing, say so clearly and explain what additional context would help.
If the user asks you about a specific study you don't have context for try to search this study by its shortname.
"""

class StudyTagCategory(str, Enum):
    """
    Category of structured tags associated with a clinical study.

    Attributes:
        interventions:
            Treatments, drugs, procedures, or actions applied within the study.
            Includes both experimental and control arm interventions.
        conditions:
            Medical conditions, diseases, or disorders targeted or studied.
            Represents the clinical focus or eligibility context of the study.
        outcomes:
            Measured endpoints or results used to evaluate study effectiveness.
            Includes primary and secondary endpoints such as efficacy or safety metrics.
    """
    INTERVENTIONS = "interventions"
    CONDITIONS = "conditions"
    OUTCOMES = "outcomes"

@dataclass
class AgentContext:
    current_report: int
    visited_candidate_studies: int
    study_repo : StudyRepository
    report_repo : ReportRepository
    study_similarity_service : StudySimilaritySearchService
    document_service :  DocumentService
    cutoff_date: str #For evaluation only

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
async def fetch_next_candidate_study(reason: str, runtime: ToolRuntime[AgentContext]) -> dict:  
    """
    Retrieve the next most relevant candidate study for the current report.

    This function queries a similarity service to rank studies related to the
    active report and returns the next unvisited study based on the internal
    visitation counter. The selection is driven by similarity to the report
    title/abstract and filtered according to previously visited candidates.

    Args:
        reason: Explanation for why the next candidate study is being requested.
            Used for logging, traceability, or agent reasoning context.

    Returns:
        dict: A dictionary containing metadata about the selected study:
            - studyId (str): Unique identifier of the study
            - shortName (str): Human-readable study name
            - trialId (str): Identifier for trial contact details
            - numberParticipants (str): Number of participants in the study
            - countries (List[str]): List of countries involved in the study
            - duration (str): Duration of the study
            - comparison (str): Comparator/intervention description
    """
    report_id = runtime.context.current_report
    visited_candidate_studies = runtime.context.visited_candidate_studies
    cutoff = runtime.context.cutoff_date
    
    response = await runtime.context.study_similarity_service.get_similar_studies_by_id(
        report_id,
        aspect='default',
        cutoff=cutoff,
        negative_reports=None,
        negative_studies=None,
        k=visited_candidate_studies + 1,
        return_details=False
    )

    study_id = response['id'][visited_candidate_studies]

    response = await runtime.context.study_repo.get_study_by_id(study_id=study_id)

    result = {
        "studyId": response.id,
        "shortName": response.short_name,
        "trialId": response.trialist_contact_details,
        "numberParticipants": response.number_participants,
        "countries": response.countries.split("//"),
        "duration": response.duration,
        "comparison": response.comparison,
    }

    runtime.context.visited_candidate_studies += 1
    return result

@tool
async def fetch_report_fulltext(
    report_id: Optional[int],
    runtime: ToolRuntime[AgentContext],
) -> str:
    """
    Retrieve the full text content of a report.

    If no report ID is provided, the function returns the full text of the
    currently active report stored in the agent context.

    Args:
        report_id: Identifier of the report whose full text should be retrieved.
            If None, the full text of the current active report is returned.

    Returns:
        str: Full text content of the report.
    """
    if report_id is None:
        return await runtime.context.document_service.get_fulltext(
            runtime.context.current_report,
            fast=False,
        )

    return await runtime.context.document_service.get_fulltext(
        report_id,
        fast=False,
    )

@tool
async def fetch_report_abstract(
    report_id: int,
    runtime: ToolRuntime[AgentContext],
) -> str:
    """
    Retrieve the abstract of a specific report.

    This function fetches the report record by its identifier and returns
    the abstract text if available.

    Args:
        report_id: Unique identifier of the report.

    Returns:
        str: The abstract text of the report, or a fallback message if no abstract is available.
    """
    response = await runtime.context.report_repo.get_report_by_id(report_id)

    if response.abstract is None:
        return "No abstract available"

    return response.abstract

@tool
async def fetch_reports_linked_to_study(
    study_id: int,
    runtime: ToolRuntime[AgentContext],
) -> List[Dict[str, str]]:
    """
    Retrieve all reports associated with a given study.

    This function returns a list of report titles linked to the specified
    study identifier.

    Args:
        study_id: Unique identifier of the study.

    Returns:
        List[Dict[str, str]]: A list of report metadata dictionaries, each containing:
            - reportId (str): Unique identifier of the report
            - title (str): Title of the report
    """
    cutoff = runtime.context.cutoff_date
    response = await runtime.context.study_repo.get_study_reports_by_study_id(study_id, cutoff=cutoff)

    return [
        {
            "reportId": item["id"],
            "title": item["title"],
        }
        for item in response
    ]
@tool
async def fetch_tags_associated_with_study(study_id: int, tag_category: StudyTagCategory,runtime: ToolRuntime[AgentContext]) -> List[str]:
    """
    Retrieve structured tags associated with a clinical study.

    This function returns standardized descriptors linked to a study,
    grouped by category (interventions, conditions, or outcomes).

    Args:
        study_id: Unique identifier of the study.
        tag_category: Type of study metadata to retrieve.

    Returns:
        List[str]: List of tag descriptions for the requested category.
    """
    if tag_category == StudyTagCategory.INTERVENTIONS:
        response = await runtime.context.study_repo.get_study_interventions_single(study_id)
    elif tag_category == StudyTagCategory.CONDITIONS:
        response = await runtime.context.study_repo.get_study_conditions_single(study_id)
    elif tag_category == StudyTagCategory.OUTCOMES:
        response = await runtime.context.study_repo.get_study_outcomes_single(study_id)
    else:
        raise ValueError(f"Unsupported tag category: {tag_category}")

    return [item["Description"] for item in response]

@tool
async def fetch_study_by_shortname(
    short_name: str,
    runtime: ToolRuntime[AgentContext],
) -> dict:
    """
    Search for a study by its short name.

    Returns a single matching study record or raises an error if none is found.

    Args:
        short_name: Shortname of the study to search for (typically first author + year / trial id / study acronym).

    Returns:
        dict: A dictionary containing study metadata with the following fields:
            - studyId (int): Unique identifier of the study
            - shortName (str): Human-readable short name of the study
            - trialId (str): Trial registration identifier
            - numberParticipants (int): Number of participants enrolled
            - countries (List[str]): List of countries involved in the study
            - duration (str): Duration of the study
            - comparison (str): Comparator or intervention description

    Raises:
        ValueError: If no study is found matching the provided short name.
    """
    cutoff = runtime.context.cutoff_date
    response = await runtime.context.study_repo.search_study_by_shortname(short_name, cutoff=cutoff)

    if response is None:
        raise ValueError(f"No study found with shortname '{short_name}'")

    return {
        "studyId": response.id,
        "shortName": response.short_name,
        "trialId": response.trial_registration_id,
        "numberParticipants": response.number_participants,
        "countries": response.countries.split("//"),
        "duration": response.duration,
        "comparison": response.comparison,
    }

@tool
async def fetch_persons_associated_with_study(
    study_id: int,
    runtime: ToolRuntime[AgentContext],
) -> List[str]:
    """
    Retrieve all persons associated with a clinical study.

    This includes individuals linked to the study such as investigators,
    collaborators, sponsors, or other recorded personnel depending on
    repository configuration.

    Args:
        study_id: Unique identifier of the study.

    Returns:
        List[str]: List of person names or identifiers associated with the study.
    """
    cutoff = runtime.context.cutoff_date
    return await runtime.context.study_repo.get_study_persons_single(study_id, cutoff=cutoff)

class BaseAgentService:
    def __init__(
        self,
        user_id: str,
        report_repo: ReportRepository,
        study_repo : StudyRepository,
        document_service :  DocumentService,
        study_similarity_service: StudySimilaritySearchService,
        checkpointer: Any,
        model: Any,
        system_prompt: str,
        thread_prefix: str,
        cutoff: Optional[str],
    ):
        self.report_repo = report_repo
        self.study_repo = study_repo
        self.study_similarity_service = study_similarity_service
        self.document_service = document_service
        self.checkpointer = checkpointer
        self.model = model
        self.thread_prefix = thread_prefix
        self.user_id = user_id
        self.cutoff = cutoff

        system_message = SystemMessage(
            content=[
                {
                    "type": "text",
                    "text": system_prompt,
                }
            ]
        )

        agent_config: Dict[str, Any] = {
            "model": self.model,
            "tools": [fetch_next_candidate_study, fetch_report_fulltext, fetch_reports_linked_to_study, fetch_tags_associated_with_study, fetch_persons_associated_with_study, fetch_report_abstract, fetch_study_by_shortname],
            "context_schema": AgentContext,
            "system_prompt": system_message,
            "checkpointer": checkpointer,
        }
        self.agent = create_agent(**agent_config)

    def _thread_id(self, report_id: int) -> str:
        return f"{self.thread_prefix}-{self.user_id}-{report_id}"

    def _agent_context(self, report_id: int, visited_candidate_studies: int) -> AgentContext:
        return AgentContext(
            current_report=report_id,
            visited_candidate_studies=visited_candidate_studies,
            study_repo=self.study_repo,
            report_repo=self.report_repo,
            study_similarity_service=self.study_similarity_service,
            document_service=self.document_service,
            cutoff_date=self.cutoff,
        )

    async def _load_report_context(self, report_id : int) -> str:
        report = await self.report_repo.get_report_by_id(report_id)
        if report is None:
            raise ValueError(f"Report {report_id} not found")

        authors = [author.strip() for author in (report.authors or "").split("//") if author.strip()]
        return (
            f"Title: {report.title or 'No title available'}\n"
            f"Abstract: {report.abstract or 'No abstract available'}\n"
            f"Authors: {', '.join(authors)}"
        )

    async def get_history(self, report_id : int) -> Any:
        config = {"configurable": {"thread_id": self._thread_id(report_id)}}
        return await self.agent.aget_state(config)
    
    async def ask_me(self, report_id : int, question : str) -> Any:
        history = await self.get_history(report_id)
        messages = getattr(history, "values", {}).get("messages", []) if history is not None else []
        visited_candidate_studies = 0

        for message in messages:
            message_name = message.get("name") if isinstance(message, dict) else getattr(message, "name", None)
            if message_name == "fetch_next_candidate_study":
                visited_candidate_studies += 1

        input_messages: List[Dict[str, str]] = []
        if not messages:
            report_string = await self._load_report_context(report_id)
            input_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Use the following report context for this conversation:\n"
                        f"{report_string}"
                    ),
                }
            )
        
        input_messages.append(
            {
                "role": "user",
                "content": question,
            }
        )

        result = await self.agent.ainvoke(
            {
                "messages": input_messages
            },
            {"configurable": {"thread_id": self._thread_id(report_id)}},
            context=self._agent_context(report_id=report_id, visited_candidate_studies=visited_candidate_studies),
        )
        return result

    async def delete_chat(self, report_id: int) -> None:
        thread_id = self._thread_id(report_id)
        await self.checkpointer.adelete_thread(thread_id)

class AutomationService(BaseAgentService):
    def __init__(
        self,
        user_id: str,
        report_repo: ReportRepository,
        study_repo : StudyRepository,
        document_service :  DocumentService,
        study_similarity_service: StudySimilaritySearchService,
        checkpointer: Any,
        model: Any,
        cutoff: Optional[str],
    ):
        super().__init__(
            user_id="",#TODO make this chat user specific
            report_repo=report_repo,
            study_repo=study_repo,
            document_service=document_service,
            study_similarity_service=study_similarity_service,
            checkpointer=checkpointer,
            model=model,
            system_prompt=SYSTEM_MESSAGE_AUTOBOT,
            thread_prefix="prediction",
            cutoff=cutoff,
        )

        structured_system_message = SystemMessage(
            content=[
                {
                    "type": "text",
                    "text": SYSTEM_MESSAGE_AUTOBOT,
                }
            ]
        )
        structured_agent_config: Dict[str, Any] = {
            "model": self.model,
            "tools": [fetch_next_candidate_study, fetch_report_fulltext, fetch_reports_linked_to_study, fetch_tags_associated_with_study, fetch_persons_associated_with_study, fetch_report_abstract, fetch_study_by_shortname],
            "system_prompt": structured_system_message,
            "checkpointer": checkpointer,
            "response_format": ToolStrategy(Output),
        }
        self.structured_agent = create_agent(**structured_agent_config)

    async def report_matching(self, report_id : int) -> ExistingStudy | NewStudy:
        print("Start report matching: ", report_id)
        report_string = await self._load_report_context(report_id)

        result = await self.structured_agent.ainvoke(
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
            {"configurable": {"thread_id": self._thread_id(report_id)}},
            context=self._agent_context(report_id=report_id, visited_candidate_studies=0),
        )
        return result['structured_response']

    async def report_matching_stream(self, report_id : int) -> AsyncGenerator[str, None]:
        """Stream agent execution events as server-sent events.
        
        Yields:
            Server-sent event formatted strings with agent execution updates
        """
        report_string = await self._load_report_context(report_id)

        async for event in self.structured_agent.astream(
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
            {"configurable": {"thread_id": self._thread_id(report_id)}},
            context=self._agent_context(report_id=report_id, visited_candidate_studies=0),
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
                    payload.append({'studyId': tool_call["args"]["study_id"], 'message': "Checking study interventions."})
                elif tool_call['name'] == "fetch_study_reports":
                    payload.append({'studyId': tool_call["args"]["study_id"], 'message': "Checking study reports."})
                elif tool_call['name'] == "fetch_current_fulltext":
                    payload.append({'studyId': None, 'message': "Reading report fulltext."})
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
    
class QuestionAnsweringService(BaseAgentService):
    def __init__(
        self,
        user_id: str,
        report_repo: ReportRepository,
        study_repo : StudyRepository,
        document_service :  DocumentService,
        study_similarity_service: StudySimilaritySearchService,
        checkpointer: Any,
        model: Any,
        cutoff: Optional[str],
    ):
        super().__init__(
            user_id=user_id,
            report_repo=report_repo,
            study_repo=study_repo,
            document_service=document_service,
            study_similarity_service=study_similarity_service,
            checkpointer=checkpointer,
            model=model,
            system_prompt=SYSTEM_MESSAGE_QUESTION_ANSWERING,
            thread_prefix="question-answering",
            cutoff=cutoff,
        )
