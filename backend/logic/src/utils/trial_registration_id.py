import re
import unicodedata

def br(pattern: str) -> str:
    #return pattern
    return rf"\b{pattern}\b"

isrctn = re.compile(br(r"ISRCTN\d\d\d\d\d\d\d\d"), re.IGNORECASE)
chictr = re.compile(br(r"ChiCTR\d\d\d\d\d\d\d\d\d\d"), re.IGNORECASE)
chictr_trc = re.compile(br(r"ChiCTR.TRC.\d\d\d\d\d\d\d\d"), re.IGNORECASE)
chictr_ior = re.compile(br(r"ChiCTR.IOR.\d\d\d\d\d\d\d\d"), re.IGNORECASE)
chictr_inr = re.compile(br(r"ChiCTR-(?:INR|IPR|POC|IIR|IOQ|OPC)-\d{8}"), re.IGNORECASE)
chictr_ipr = re.compile(br(r"ChiCTR-IPR-\d\d\d\d\d\d\d\d"), re.IGNORECASE)
actrn = re.compile(br(r"ACTR(?:N|\d)\d{14}"), re.IGNORECASE)

ctri = re.compile(br(r"CTRI(?:/|-)\d{4}(?:/|-)\d{2,3}(?:/|-)\d{6}"), re.IGNORECASE)

nct = re.compile(br(r"NCT(?:\W)?\d{7,8}"), re.IGNORECASE)
drks = re.compile(br(r"DRKS\d\d\d\d\d\d\d\d"), re.IGNORECASE)

nlomon = re.compile(br(r"NL-OMON\d\d\d\d\d"), re.IGNORECASE)
nl = re.compile(br(r"NL\d\d\d\d"), re.IGNORECASE)
irct = re.compile(br(r"IRCT\d\d\d\d\d\d\d\d\d\d\d\d\d?\d?N\d+"), re.IGNORECASE)
kct = re.compile(br(r"KCT\d\d\d\d\d\d\d"), re.IGNORECASE)
tctr = re.compile(br(r"TCTR\d\d\d\d\d\d\d\d\d\d\d"), re.IGNORECASE)
rbr = re.compile(br(r"RBR-[a-z0-9]{6,7}"), re.IGNORECASE)
ctis = re.compile(br(r"CTIS\d\d\d\d-\d\d\d\d\d\d-\d\d-\d\d"), re.IGNORECASE)
jprn_umin = re.compile(br(r"(?:JPRN-)?UMIN\d\d\d\d\d\d\d\d\d"), re.IGNORECASE)
jprn_japic = re.compile(br(r"(?:JPRN-)?JapicCTI-\d{6}"), re.IGNORECASE)
jprn_jrct = re.compile(br(r"JPRN-jRCTs?\d\d\d\d\d\d\d\d\d\d?"), re.IGNORECASE)
euctr = re.compile(br(r"EUCTR\d{4}-\d{6}-\d{2}"), re.IGNORECASE)
itmctr = re.compile(br(r"ITMCTR\d\d\d\d\d\d\d\d\d\d"), re.IGNORECASE)
pactr = re.compile(br(r"PACTR\d\d\d\d\d\d\d\d\d\d\d\d\d\d\d"), re.IGNORECASE)
ntr = re.compile(br(r"NTR\d\d\d\d?"), re.IGNORECASE)
ukcrnid = re.compile(br(r"UKCRNID\d\d\d\d\d?"), re.IGNORECASE)
slctr = re.compile(br(r"SLCTR-\d\d\d\d-\d\d\d"), re.IGNORECASE)
hkctr = re.compile(br(r"HKCTR-\d\d\d\d"), re.IGNORECASE)
m = re.compile(br(r"M\d\d-\d\d\d"), re.IGNORECASE)
mct = re.compile(br(r"MCT-\d\d\d\d\d"), re.IGNORECASE)

fid = re.compile(br(r'F1D-[A-Z]{2}-[A-Z0-9]{4}'), re.IGNORECASE)
ris = re.compile(br(r'RIS-[A-Z]{3}-\d+'), re.IGNORECASE)

all_registration_id_patterns = [isrctn, chictr, chictr_trc, chictr_ior, actrn, ctri, nct, drks, nlomon,nl, irct, kct, tctr, rbr, ctis, jprn_umin, jprn_jrct, jprn_japic, euctr, itmctr, pactr, ntr, chictr_inr, chictr_ipr, ukcrnid, slctr, hkctr, m, mct, fid, ris]

def extract_trial_ids_from_text(text):
    text = unicodedata.normalize("NFC", text)

    def extract(clean_text):
        matches = []
        for pattern in all_registration_id_patterns:
            for match in re.finditer(pattern, clean_text):
                trial_id = match.group().replace("#", "")
                matches.append(trial_id)
        return matches
    
    clean_text_1 = re.sub(r"[\u2000-\u200f\u202f\u2060]", "", text)
    clean_text_1 = clean_text_1.replace("\xa0", " ").replace("\u202f", " ")
    
    clean_text_2 = text.encode('ascii', 'ignore').decode('ascii')
    clean_text_2 = clean_text_2.replace("\n", " ").replace("\t", " ")

    clean_all = re.sub(r'[^A-Za-z0-9 ]+', '', text)
    
    
    matches = []
    matches = [m for m in matches if m[0] != -1]
    for item in extract(clean_text_1) + extract(clean_text_2):
        pos = clean_all.find(re.sub(r'[^A-Za-z0-9 ]+', '', item))
        matches.append((pos, item))

    matches.sort(key=lambda x: x[0])

    # Remove duplicates, preserving order
    seen = set()
    ordered_ids = []
    for _, trial_id in matches:
        if trial_id not in seen:
            seen.add(trial_id)
            ordered_ids.append(trial_id)
    return ordered_ids

def extract_trial_id(title, abstract, authors):
    all_ids = []
    if title:
        all_ids.extend(extract_trial_ids_from_text(title.replace("\n", "")))

    if authors:
        for author in authors:
            all_ids.extend(extract_trial_ids_from_text(author))
    if abstract:
        all_ids.extend(extract_trial_ids_from_text(abstract.replace("\n", "")))
    
    # Remove duplicates while preserving order
    seen = set()
    ordered_ids = []
    for trial_id in all_ids:
        if trial_id not in seen:
            seen.add(trial_id)
            ordered_ids.append(trial_id)
    return ordered_ids