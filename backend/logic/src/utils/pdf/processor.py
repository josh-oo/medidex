import asyncio
import fitz
import os
import re
import json
import aiofiles
from rapidfuzz import fuzz
from ..trial_registration_id import extract_trial_ids_from_text

STUDY_ACRONYMS = ['ACE' 'AIM-TD' 'ALPINE' 'ARM-TD' 'CATIE' 'CHANGE' 'CUtLASS-1' 'CUtLASS-2'
'DEFASLP' 'DREaM' 'EAGLES' 'EDIE' 'EDIE-2' 'EDIE-NL' 'EPISODE II'
 'EUFEST' 'EULAST' 'KINECT 3' 'MATISSE' 'NEURAPRO' 'NeSSy' 'OPTiMiSE'
 'OPUS' 'OPUS II' 'PRIME' 'RAISE-ETP' 'RISE' 'SOCRATES' 'Straight' 'TEOSS'
 'TREC-Lebanon' 'TREC-Rio-I' 'TREC-Rio-II' 'TREC-Vellore-I'
 'TREC-Vellore-II' 'TREC-Vellore-III' 'YES' 'gameChange']

def identify_abstract_collection(path : str):
    """
    gets pdf_file_path
    returns if it is an abstract collection and the number of pages
    """

    #a dict of suspicious abstract collection patterns and their corresponding "occurences per page"
    PATTERNS_PER_PAGE = {
                     r"\n[A-Z]\.\d\.[a-z]\.\d\d\d\s": 2,
                     r"\nPS\d\d-\d\d\d\n" : 2,
                     r"BIOL PSYCHIATRY [0-9][0-9][0-9][0-9].*S": 1,
                     r"ACNP [0-9][0-9][0-9][0-9] Annual Meeting": 1,
                     r"\nP[0-9]+\n" : 3,
                     r"\nO[0-9][0-9][A-Z]?\n": 3,
                     r"\nS-?[0-9][0-9]-?[0-9][0-9]\s": 2,
                     r"\n[A-Z]-[0-9][0-9]-[0-9][0-9][0-9]\s":2,
                     r"Talk\s[0-9]+\n":2,
                     r"Poster\s[0-9]+\n":2,
                     r"SIRS [0-9][0-9][0-9][0-9] Abstracts": 1,
                     r"\s[A-Z][0-9][0-9]\.[0-9][0-9]:?\s": 2,
                     r"\n[A-Z][A-Z_\W]*\n([A-Z]\.\s?)+ [A-Za-z]*(,|\n)": 2,
                     r"\n[A-Z][A-Z_\W]*\n[A-Z][A-Za-z-]+ ([A-Z]\. )*[A-Z][A-Za-z-]+," : 2,
                     r"(?i)summary": 3,
                     r"(?i)references": 3,
                     r"(?i)CORRESPONDING":2,
                     r"Year.*Volume.*Issue.*Pages.*Abstract.*www.pdffactory.com": 1,
                     "doi:10.1016":2,
                     "Symposium of AGNP, Nuremberg": 0.85,
                     "International Conference on Early Psychosis":0.9,
                     "International Congress on Schizophrenia Research": 0.9,
                     "Abstracts of the _ Biennial Schizophrenia International Research Conference / Schizophrenia Research": 0.85,
                     "Abstracts for the": 0.9,
                     "CONFERENCE SUMMARY": 0.9,
                     "Chairman": 0.9,
                     #"www.nrr.nhs.uk":-1
                     }
                     #Not found:
                     #cleaned_Tarrier 1996 - The use of cognitive behaviour.pdf
                     #cleaned_Bell, Milstein et al. 1993 - Pay and participation in work.pdf
                     #cleaned_Matthews 1981 - The process and outcome.pdf (last two pages)
    
    found_words = []
    num_pages = 0
    try:
        with fitz.open(path) as pdf:
            #process every single page
            for page_num in range(len(pdf)):
                page = pdf[page_num]
                page_text = page.get_text()
                for key, threshold in PATTERNS_PER_PAGE.items():
                    #look for all marker pattersn in the dict
                    if threshold < 0: #just look for one occurence in the whole document
                        if key in page_text:
                            return True, len(pdf)
                    elif threshold > 0 and threshold < 1: #we can do fuzzy search in this case
                        ratio = fuzz.partial_ratio(key.lower(), page_text.lower())
                        if ratio > threshold * 100:
                            found_words.append(key)
                    else:
                        pattern = re.compile(key)
                        results = pattern.findall(page_text)
                        if len(results) >= threshold:
                            found_words.append(key)
                num_pages += 1
    except:
        pass
        
    for key in PATTERNS_PER_PAGE.keys():
        #return true if the requirements are met on every second page:
        if found_words.count(key) > (num_pages-1)/2.0:
            return True
    return False

async def extract_text_from_pdf(path: str) -> str:
    def _sync_extract():
        try:
            doc = fitz.open(path)
            parts = []
            for page in doc:
                parts.append(page.get_text() or "")
            doc.close()
            return "".join(parts)  # no newline characters
        except fitz.FileDataError:
            return ""
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""
    return await asyncio.to_thread(_sync_extract)


async def extract_trial_ids_pdf(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    
    text = await extract_text_from_pdf(path)
    return extract_trial_ids_from_text(text)

def extract_study_acronyms(text):
    acronyms = []
    for acronym in STUDY_ACRONYMS:
        if acronym in text:
            acronyms.append(acronym)
    return acronyms

async def process_pdf(in_folder : str, out_folder : str, filename : str):
    pdf_path = os.path.join(in_folder, filename + ".pdf")
    if identify_abstract_collection(pdf_path):
        meta_data = {'trial_id' : [], 'study_acronyms': [], 'report_type': 'abstract'}
        json_path = os.path.join(out_folder, filename + ".json")

        async with aiofiles.open(json_path, "w") as f:
            await f.write(json.dumps(meta_data, indent=2))

        return meta_data

    text = await extract_text_from_pdf(pdf_path)
    trial_ids = extract_trial_ids_from_text(text)
    study_acronyms = extract_study_acronyms(text)

    #TODO add LLM extraction here

    meta_data = {'trial_id' : trial_ids, 'study_acronyms': study_acronyms}
    json_path = os.path.join(out_folder, filename + ".json")

    async with aiofiles.open(json_path, "w") as f:
        await f.write(json.dumps(meta_data, indent=2))

    return meta_data
