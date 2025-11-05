import re

def extract_trial_registration_ids(text):
    isrctn = re.compile(r"\bISRCTN\d\d\d\d\d\d\d\d\b")
    chictr = re.compile(r"\bChiCTR\d\d\d\d\d\d\d\d\d\d\b")
    chictr_trc = re.compile(r"\bChiCTR.TRC.\d\d\d\d\d\d\d\d\b")
    chictr_ior = re.compile(r"\bChiCTR.IOR.\d\d\d\d\d\d\d\d\b")
    chictr_inr = re.compile(r"\bChiCTR-(?:INR|IPR|POC|IIR|IOQ|OPC)-\d{8}\b")
    chictr_ipr = re.compile(r"\bChiCTR-IPR-\d\d\d\d\d\d\d\d\b")
    actrn = re.compile(r"\bACTR(?:N|\d)\d{14}\b")

    ctri = re.compile(r"\bCTRI(?:/|-)\d{4}(?:/|-)\d{2,3}(?:/|-)\d{6}\b")

    nct = re.compile(r"\b[Nn][Cc][Tt].?0*[1-9]\d{0,7}\b")
    drks = re.compile(r"\bDRKS\d\d\d\d\d\d\d\d\b")

    nlomon = re.compile(r"\bNL-OMON\d\d\d\d\d\b")
    nl = re.compile(r"\bNL\d\d\d\d\b")
    irct = re.compile(r"\bIRCT\d\d\d\d\d\d\d\d\d\d\d\d\d?\d?N\d+\b")
    kct = re.compile(r"\bKCT\d\d\d\d\d\d\d\b")
    tctr = re.compile(r"\bTCTR\d\d\d\d\d\d\d\d\d\d\d\b")
    rbr = re.compile(r"\bRBR-.......\b")
    ctis = re.compile(r"\bCTIS\d\d\d\d-\d\d\d\d\d\d-\d\d-\d\d\b")
    jprn_umin = re.compile(r"\b(?:JPRN-)?UMIN\d\d\d\d\d\d\d\d\d\b")
    jprn_japic = re.compile(r"\b(?:JPRN-)?JapicCTI-\d{6}\b")
    jprn_jrct = re.compile(r"\bJPRN-jRCTs?\d\d\d\d\d\d\d\d\d\d?\b")
    euctr = re.compile(r"\bEUCTR\d{4}-\d{6}-\d{2}\b")
    itmctr = re.compile(r"\bITMCTR\d\d\d\d\d\d\d\d\d\d\b")
    pactr = re.compile(r"\bPACTR\d\d\d\d\d\d\d\d\d\d\d\d\d\d\d\b")
    ntr = re.compile(r"\bNTR\d\d\d\d?\b")
    ukcrnid = re.compile(r"\bUKCRNID\d\d\d\d\d?\b")
    slctr = re.compile(r"\bSLCTR-\d\d\d\d-\d\d\d\b")
    hkctr = re.compile(r"\bHKCTR-\d\d\d\d\b")
    m = re.compile(r"\bM\d\d-\d\d\d\b")
    mct = re.compile(r"\bMCT-\d\d\d\d\d\b")

    all_registration_id_patterns = [isrctn, chictr, chictr_trc, chictr_ior, actrn, ctri, nct, drks, nlomon,nl, irct, kct, tctr,rbr, ctis, jprn_umin, jprn_jrct, jprn_japic, euctr, itmctr, pactr, ntr, chictr_inr, chictr_ipr, ukcrnid, slctr, hkctr, m, mct]

    all_results = []
    for pattern in all_registration_id_patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            m = m.replace("#", "")
            all_results.append(m)

    return list(set(all_results))