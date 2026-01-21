from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from pydantic import BaseModel, Field
from typing import List, Any
import enum

model = ChatOpenAI(model="gpt-4.1-mini")

class PicoDataExtraction(BaseModel):
    """Contact information for a person."""
    trial_id : List[str] = Field(description="The trial registration ID associated with this study")
    number_of_participants: int | None = Field(description="The total number of participants beeing part of the study")
    duration : int | None = Field(description="The duration of the intervention in seconds")
    countries : List[str] = Field(description="The countries where the study takes place")
    interventions: List[str] = Field(description="Every arms (including control group) intervention evaluated in the study (only one per arm, if there is one arm with multiple interventions use the word 'combined'), return as few words as possible ignore extra information about duration and dosage")
    conditions: List[str] = Field(description="The elegible particpants conditions (nouns and adjectives)")
    outcomes: List[str] = Field(description="The outcomes of this study")
    authors : List[str] = Field(description="The authors associated with this article (lastname + firstname initials for example: 'Nicolaas P A Zuithoff' -> 'Zuithoff NPA')")

model_with_extraction_structure = model.with_structured_output(PicoDataExtraction)

extract_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a clinical research expert. "
        "Extract PICO-style structured data strictly from the provided inputs. "
        "First, extract information from the TITLE and ABSTRACT. "
        "Then, use the FULL TEXT to confirm, validate, correct, or complete the information from the TITLE and ABSTRACT. "
        "If a field is missing or unclear after checking the FULL TEXT, leave it empty or infer conservatively. "
        "Do not make up something, use the exact same phrases from the source. "
    ),
    (
        "human",
        "Title: {title}\n\nAbstract: {abstract}\n\nFull Text: {document_text}"
    )
])

extract_chain = extract_prompt | model_with_extraction_structure

class Confidence(str, enum.Enum):
    high = 'high'
    medium = 'medium'
    low = 'low'

class VocabularyMatch(BaseModel):
    original: str = Field(description="The original term")
    selected_id: int | None = Field(description="The ID of the selected item leave empty")
    selected_keyword: str | None = Field(description="The keyword description of the selected item")
    confidence: Confidence = Field(description="How confident are you that the selected item matches the extracted term (high, medium, low)")

model_with_selection_structure = model.with_structured_output(VocabularyMatch)

select_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You map extracted clinical terms to a controlled vocabulary.\n"
     "Rules:\n"
     "- Prefer the provided candidates\n"
     "- Prefer exact semantic equivalence\n"
     "- If you didn't find a matching term leave the corresponding references empty\n"
     "- Return all relevant matches (in rare cases there are more than one matches per extracted term)\n"
     ),
    ("human",
     "Extracted term:\n{term}\n\n"
     "Candidates:\n{candidates}")
])

select_chain = select_prompt | model_with_selection_structure

async def extract_pico(title : str, abstract : str, fulltext: str):
    result = await extract_chain.ainvoke({
        "title": title,
        "abstract":abstract,
        "document_text": fulltext
    })
    return result

async def find_match(term : str, candidates : List[Any]):
    result = await select_chain.ainvoke({
        "term": term,
        "candidates":candidates,
    })
    return result

