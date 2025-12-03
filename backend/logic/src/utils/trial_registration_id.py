import re

def extract_trial_registration_ids(text):
    isrctn = re.compile(r"\bISRCTN\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    chictr = re.compile(r"\bChiCTR\d\d\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    chictr_trc = re.compile(r"\bChiCTR.TRC.\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    chictr_ior = re.compile(r"\bChiCTR.IOR.\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    chictr_inr = re.compile(r"\bChiCTR-(?:INR|IPR|POC|IIR|IOQ|OPC)-\d{8}\b", re.IGNORECASE)
    chictr_ipr = re.compile(r"\bChiCTR-IPR-\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    actrn = re.compile(r"\bACTR(?:N|\d)\d{14}\b", re.IGNORECASE)

    ctri = re.compile(r"\bCTRI(?:/|-)\d{4}(?:/|-)\d{2,3}(?:/|-)\d{6}\b", re.IGNORECASE)

    nct = re.compile(r"\b[Nn][Cc][Tt].?0*[1-9]\d{0,7}\b", re.IGNORECASE)
    drks = re.compile(r"\bDRKS\d\d\d\d\d\d\d\d\b", re.IGNORECASE)

    nlomon = re.compile(r"\bNL-OMON\d\d\d\d\d\b", re.IGNORECASE)
    nl = re.compile(r"\bNL\d\d\d\d\b", re.IGNORECASE)
    irct = re.compile(r"\bIRCT\d\d\d\d\d\d\d\d\d\d\d\d\d?\d?N\d+\b", re.IGNORECASE)
    kct = re.compile(r"\bKCT\d\d\d\d\d\d\d\b", re.IGNORECASE)
    tctr = re.compile(r"\bTCTR\d\d\d\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    rbr = re.compile(r"\bRBR-.......\b", re.IGNORECASE)
    ctis = re.compile(r"\bCTIS\d\d\d\d-\d\d\d\d\d\d-\d\d-\d\d\b", re.IGNORECASE)
    jprn_umin = re.compile(r"\b(?:JPRN-)?UMIN\d\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    jprn_japic = re.compile(r"\b(?:JPRN-)?JapicCTI-\d{6}\b", re.IGNORECASE)
    jprn_jrct = re.compile(r"\bJPRN-jRCTs?\d\d\d\d\d\d\d\d\d\d?\b", re.IGNORECASE)
    euctr = re.compile(r"\bEUCTR\d{4}-\d{6}-\d{2}\b", re.IGNORECASE)
    itmctr = re.compile(r"\bITMCTR\d\d\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    pactr = re.compile(r"\bPACTR\d\d\d\d\d\d\d\d\d\d\d\d\d\d\d\b", re.IGNORECASE)
    ntr = re.compile(r"\bNTR\d\d\d\d?\b", re.IGNORECASE)
    ukcrnid = re.compile(r"\bUKCRNID\d\d\d\d\d?\b", re.IGNORECASE)
    slctr = re.compile(r"\bSLCTR-\d\d\d\d-\d\d\d\b", re.IGNORECASE)
    hkctr = re.compile(r"\bHKCTR-\d\d\d\d\b", re.IGNORECASE)
    m = re.compile(r"\bM\d\d-\d\d\d\b", re.IGNORECASE)
    mct = re.compile(r"\bMCT-\d\d\d\d\d\b", re.IGNORECASE)

    all_registration_id_patterns = [isrctn, chictr, chictr_trc, chictr_ior, actrn, ctri, nct, drks, nlomon,nl, irct, kct, tctr,rbr, ctis, jprn_umin, jprn_jrct, jprn_japic, euctr, itmctr, pactr, ntr, chictr_inr, chictr_ipr, ukcrnid, slctr, hkctr, m, mct]

    all_results = []
    for pattern in all_registration_id_patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            m = m.replace("#", "")
            all_results.append(m)

    return list(set(all_results))