import re
import os
import json
from typing import List

from nameparser import HumanName
import unicodedata

from dotenv import load_dotenv

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

def load_trial_person_mapping():
    file_path = os.path.join(DATABASE_VOLUME,"resources", "trial_person_mapping.json")
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as json_file:
        return json.load(json_file)
    
trial_person_mapping = load_trial_person_mapping()

def normalize_author_names(authors: List[str]) -> List[str]:
    def get_person_from_trial_id(author):
        author = author.strip()
        trial_id = author.replace("/", "-")
    
        if trial_id not in trial_person_mapping:
            return [author]
        authors = trial_person_mapping[trial_id]

        processed_authors = []
        for author in authors:
            hn = HumanName(author)
            # Get last name
            last = hn.last
    
            # Get initials (first and middle names)
            initials = ''.join(part[0].upper() for part in [hn.first, hn.middle] if part)

            processed_authors.append(f"{last} {initials}")

        return list(set(processed_authors))
    
    def normalize_author_name(name):
        # Basic prep
        name = name.strip()
        name = unicodedata.normalize('NFKC', name)

        if re.search(r'\d', name):
            return None

        # Transform: Remove everything except letters
        clean_name = re.sub(r'[^a-zA-Z]', '', name)

        if not clean_name:
            return None

        # Validate: Start Upper, End Upper, Contains Lower
        if (clean_name[0].isupper() and 
            clean_name[-1].isupper() and 
            any(c.islower() for c in clean_name)):
            
            return clean_name
        
        return None

    normalized_authors = []
    for author in authors:
        current_authors = [author]
        if author in trial_person_mapping:
            current_authors = get_person_from_trial_id(author)
        for current_author in current_authors:
            normalized_author = normalize_author_name(current_author)
            if normalized_author:
                normalized_authors.append(normalized_author)
    
    return normalized_authors