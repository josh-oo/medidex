from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from pydantic import BaseModel, Field
from typing import List

model = ChatOpenAI(model="gpt-4.1-mini")

class PicoDataExtraction(BaseModel):
    """Contact information for a person."""
    trial_id : List[str] = Field(description="The trial registration ID associated with this study")
    number_of_participants: int = Field(description="The total number of participants beeing part of the study")
    interventions: List[str] = Field(description="The interventions evaluated in the study (nouns)")
    conditions: List[str] = Field(description="The elegible particpants conditions (nouns and adjectives)")
    outcomes: List[str] = Field(description="The outcomes of this study")
    authors : List[str] = Field(description="The authors associated with this article (lastname + firstname initials for example: 'Nicolaas P A Zuithoff' -> 'Zuithoff NPA')")

model_with_structure = model.with_structured_output(PicoDataExtraction)

prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a clinical research expert. "
        "Extract PICO-style structured data strictly from the provided document. "
        "First, extract information from the TITLE and ABSTRACT. "
        "Then, use the FULL TEXT to confirm, validate, or correct the information from the TITLE and ABSTRACT. "
        "If a field is missing or unclear after checking the FULL TEXT, leave it empty or infer conservatively."
    ),
    (
        "human",
        "Title: {title}\n\nAbstract: {abstract}\n\nFull Text: {document_text}"
    )
])

chain = prompt | model_with_structure

async def extract_pico(title : str, abstract : str, fulltext: str):
    result = await chain.ainvoke({
        "title": title,
        "abstract":abstract,
        "document_text": fulltext
    })
    return result

