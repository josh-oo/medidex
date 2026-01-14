from openai import OpenAI
import os
from dotenv import load_dotenv
import httpx
import asyncio
import re
import base64

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEERKAT_KEY = os.getenv("MEERKAT_KEY")

PROMPT_TEMPLATE = f"""As a medical research expert, rate the relevance of each {{CATEGORY}} to this medical study on a scale of 0.000 to 1.000.

Study Title: {{TITLE}}
Study Abstract: {{ABSTRACT}}

{{CATEGORY}}s to evaluate:
{{ASPECT_LIST}}

Consider the following factors:
- Direct mention or clear implication in the study
- Clinical relevance and therapeutic importance
- Methodological appropriateness for the study design
- Evidence strength and statistical significance
- Potential for clinical translation
- Safety and efficacy considerations

For each {{CATEGORY}}, provide a precise relevance score between 0.000 and 1.000. Avoid giving exactly 0.0, 0.5 or 1.0 unless absolutely certain. Use the following guidelines:
- 0.9-1.0: Directly mentioned and central to the study
- 0.7-0.8: Strongly implied or highly relevant
- 0.5-0.6: Moderately relevant or tangentially related
- 0.3-0.4: Weakly relevant or speculative connection
- 0.0-0.2: Not relevant or contradictory

Return ONLY the scores in this exact format: 1:0.854 2:0.323 3:0.912 4:0.432 5:0.753"""

client = OpenAI(api_key=OPENAI_API_KEY)


def clean_intervention_name(name: str) -> str:
    """
    Clean intervention names by standardizing format.
    
    Removes:
    - Prefix patterns like "C - ", "Aspect - ", "Route - ", etc.
    - Content in curly braces like "{CBT}"
    - Content in parentheses like "(Cognitive Remediation)"
    - Extra whitespace
    
    Args:
        name: Original intervention name
        
    Returns:
        Cleaned intervention name
        
    Examples:
        >>> clean_intervention_name("C - Cognitive Behavioral Therapy {CBT}")
        "Cognitive Behavioral Therapy"
        >>> clean_intervention_name("Aspect - Therapy")
        "Therapy"
        >>> clean_intervention_name("Route - Oral")
        "Oral"
        >>> clean_intervention_name("Cognitive Training (Cognitive Remediation)")
        "Cognitive Training"
    """
    # Remove specific intervention prefixes
    prefixes_to_remove = [
        'Aspect -',
        'Route -',
        'Media -',
        'Setting -',
        'Focus -',
        'Form -',
        'Media Method -'
    ]
    
    cleaned = name
    for prefix in prefixes_to_remove:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    
    # Remove single letter prefix patterns like "C - "
    cleaned = re.sub(r'^[A-Z]\s*-\s*', '', cleaned)
    
    # Remove content in curly braces
    cleaned = re.sub(r'\{[^}]*\}', '', cleaned)
    
    # Remove content in parentheses (both closed and unclosed)
    # First remove complete pairs (may be nested)
    while '(' in cleaned and ')' in cleaned:
        old_cleaned = cleaned
        cleaned = re.sub(r'\([^)]*\)', '', cleaned)
        if cleaned == old_cleaned:  # No more complete pairs
            break
    
    # Then remove any remaining unmatched opening parenthesis and everything after
    cleaned = re.sub(r'\([^)]*$', '', cleaned)
    
    # Remove extra spaces and normalize
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Remove leading/trailing non-alphanumeric characters except hyphens
    cleaned = re.sub(r'^[^\w\s-]+|[^\w\s-]+$', '', cleaned).strip()
    
    return cleaned


async def prepare_prompt(report_id):

  async with httpx.AsyncClient(base_url="http://127.0.0.1:8002", headers = {'X-API-Key': MEERKAT_KEY}) as client:
    response =  await client.get(f"/reports/{report_id}")
    response.raise_for_status()

    result = response.json()

    title = result['Title']
    abstract = result['Abstract']

    aspect_candidates = await client.get(f"/reports/{report_id}/similar_studies/tags", params={'k': 50, 'aspect': "interventions"})
    aspect_candidates.raise_for_status()
    aspect_candidates = [str(i+1) + ": " + clean_intervention_name(item['name']) for i, item in enumerate(aspect_candidates.json())]

    return PROMPT_TEMPLATE.format(CATEGORY="intervention", TITLE=title, ABSTRACT=abstract, ASPECT_LIST="\n".join(aspect_candidates))

async def get_pdf(report_id):
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8002", headers = {'X-API-Key': MEERKAT_KEY}) as client:
        response = await client.get(f"/reports/{report_id}/pdf")
        response.raise_for_status()  # optional but recommended

        pdf_bytes = response.content
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        return pdf_base64


async def extract_aspects(report_id):

    prompt = await prepare_prompt(report_id)

    pdf_file = await get_pdf(report_id)

    response = client.responses.create(
        model="gpt-5",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": "fulltext.pdf",
                        "file_data": f"data:application/pdf;base64,{pdf_file}",
                    },
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                ],
            },
        ]
    )

    response.json()

