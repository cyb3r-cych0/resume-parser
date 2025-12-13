"""
helpers/semantic_extraction.py

Unified semantic candidate scoring + structured extractors:
- build_final_schema(raw_text, canonical_sections, nlp=None, embed_model=None)
Returns: dict matching your schema (normalized keys), per-field confidences, timings.

Offline-friendly: embeddings and spaCy are optional.
"""

import re
import time
from collections import defaultdict, Counter
from typing import Dict, Any, List, Tuple, Optional

# optional imports (safe)
try:
    import spacy
except Exception:
    spacy = None

try:
    from sentence_transformers import SentenceTransformer
    import numpy as _np
    _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    _USE_EMBED = True
except Exception:
    _EMBED_MODEL = None
    _USE_EMBED = False

# ---------- simple utilities ----------
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s\(\)]{5,}\d)")
UNIV_HINT = re.compile(r"\b(university|college|institute|school|faculty|polytechnic)\b", re.I)
DEGREE_HINT = re.compile(r"\b(bachelor|bsc|bs|ba|master|msc|ms|mba|phd|associate|diploma)\b", re.I)
CERT_HINT = re.compile(r"\b(certif|certificate|certified|pmp|six sigma|training|badge|award)\b", re.I)
ORG_HINT = re.compile(r"\b(inc|ltd|llc|company|corp|co\.|group|agency)\b", re.I)
TOOL_KEYWORDS = {"kettle","pentaho","toad","rational rose","ms visio","xml spy","rational","visio","toad"}

def clean_line(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def split_lines(text: str) -> List[str]:
    return [clean_line(l) for l in re.split(r"\n|\r", text) if clean_line(l)]

def embed_text(text: str):
    if not _USE_EMBED or not text:
        return None
    try:
        return _EMBED_MODEL.encode(text, convert_to_numpy=True)
    except Exception:
        return None

def cos_sim(a, b):
    try:
        return float(_np.dot(a,b) / ((_np.linalg.norm(a)*_np.linalg.norm(b))+1e-12))
    except Exception:
        return 0.0

# add helper near other utilities
def _sanitize_name(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    # remove common trailing labels that sometimes get appended
    s = re.sub(r"\b(email|e-mail|phone|tel|contact|mobile|fax)\b[:\s\-]*$","", s, flags=re.I).strip()
    # remove stray "Email" if newline-joined input happened
    s = re.sub(r"[\r\n]+.*", "", s).strip()
    # drop if obviously not a person (contains 'Visa', 'Status', 'Nov 2025' etc.)
    if re.search(r"\b(visa|status|nov|dec|jan|feb|present|pursuing|apply)\b", s, re.I):
        return ""
    return s


# ---------- candidate extraction ----------
def collect_candidates(raw_text: str, canonical_sections: Dict[str,str]) -> Dict[str, List[Dict[str,Any]]]:
    """
    Collect raw candidate strings for target fields from sections and raw text.
    Returns dict of field -> list of candidate dicts {text, source_section, index, snippet}
    """
    cand = defaultdict(list)
    # global quick hits: email, phone
    emails = EMAIL_RE.findall(raw_text)
    phones = PHONE_RE.findall(raw_text)
    if emails:
        cand["email"].append({"text": emails[0], "source":"global", "reason":"regex_email"})
    if phones:
        # join phone groups into string
        p = phones[0]
        ph = "".join(p) if isinstance(p, tuple) else p
        cand["phoneNumber"].append({"text": ph, "source":"global", "reason":"regex_phone"})

    # collect lines per canonical section
    for sec_label, sec_text in canonical_sections.items():
        lines = split_lines(sec_text or "")
        for i, line in enumerate(lines):
            low = line.lower()
            # name candidate: header / summary top lines (heuristic)
            if sec_label in ("contact", "summary") and i < 4:
                # stricter: short line, mostly alphabetic tokens, not keywords like 'visa','status','address'
                words = [w for w in line.split() if w.isalpha() or any(ch.isalpha() for ch in w)]
                low_line = line.lower()
                # stricter: short line, mostly alphabetic tokens, not keywords like 'visa','status','certificate'
                blacklist = ("visa", "status", "address", "dob", "date of birth", "nationality", "marital",
                             "certificate", "certified", "training", "nov", "202")
                if 1 < len(words) <= 5 and all(len(w) <= 30 for w in words) and not any(
                        k in low_line for k in blacklist):
                    if any(tok[0].isupper() for tok in line.split() if tok):
                        cand["name"].append(
                            {"text": line, "source": sec_label, "index": i, "reason": "heading_or_contact_strict"})

            # education clues
            if UNIV_HINT.search(line) or DEGREE_HINT.search(line) or YEAR_RE.search(line):
                cand["ugCollegeName"].append({"text":line, "source":sec_label, "index":i, "reason":"edu_hint"})
                cand["education_raw"] = cand.get("education_raw",[]) + [{"text":line,"section":sec_label,"index":i}]
            # experience clues (title/company/date)
            if sec_label in ("experience","work","employment","other"):
                # dates or capitalized short lines indicate title/org
                if YEAR_RE.search(line) or ORG_HINT.search(line) or (len(line.split())<=6 and line==line.title()):
                    cand["work_candidates"] = cand.get("work_candidates",[]) + [{"text":line,"section":sec_label,"index":i}]
            # certifications
            if CERT_HINT.search(line) or ("certificate" in low or "pmp" in low):
                cand["certifications"].append({"text":line,"source":sec_label,"index":i,"reason":"cert_hint"})
            # skills heuristics: many commas or 'skills' section
            if sec_label in ("skills","technical","other") or ("," in line and len(line.split(","))>2 and len(line.split())<40):
                cand["skills_candidates"] = cand.get("skills_candidates",[]) + [{"text":line,"source":sec_label,"index":i}]
            # summary / profile
            if sec_label in ("summary","profile","about") or (i==0 and sec_label in ("contact","other")):
                cand["summary_candidates"] = cand.get("summary_candidates",[]) + [{"text":line,"source":sec_label,"index":i}]
            # fallback: attempt to discover email/phone inside any line
            if EMAIL_RE.search(line) and not cand.get("email"):
                cand["email"].append({"text":EMAIL_RE.search(line).group(0),"source":sec_label,"index":i})
            # replace phone extraction logic with this robust snippet
            all_phone_matches = PHONE_RE.findall(raw_text)
            # PHONE_RE may return tuples if groups present; normalize
            candidates = []
            for m in PHONE_RE.finditer(raw_text):
                ph = m.group(0)
                ph_clean = re.sub(r"[^\d\+]", "", ph)
                if len(ph_clean) >= 6:  # len threshold
                    candidates.append(ph_clean)
            # pick the longest candidate
            if candidates:
                ph_best = max(candidates, key=lambda s: len(s))
                cand["phoneNumber"].append({"text": ph_best, "source": "global", "reason": "regex_phone_longest"})

    # Also scan raw_text for degree-like lines
    for line in split_lines(raw_text):
        if DEGREE_HINT.search(line) and len(line.split())<20:
            cand["degree_candidates"] = cand.get("degree_candidates",[])+[{"text":line,"source":"raw","index":0}]
    return cand

# ---------- scoring helpers ----------
def length_penalty(txt: str, ideal=6):
    words = len(txt.split())
    if words <= ideal:
        return 1.0
    # penalty scales 0.9 -> 0.2
    pen = max(0.2, 1.0 - (words-ideal)/max(ideal, words))
    return pen

def regex_score(txt: str, field: str):
    s = 0.0
    t = txt.lower()
    if field=="ugCollegeName" or field=="pgCollegeName":
        if UNIV_HINT.search(t): s += 0.6
        if DEGREE_HINT.search(t): s += 0.15
        if YEAR_RE.search(t): s += 0.05
    if field=="name":
        # likely capitalized and <=4 tokens
        if len(txt.split())<=4 and txt==txt.title(): s += 0.6
    if field=="certifications":
        if CERT_HINT.search(t): s += 0.7
    return min(1.0, s)

def section_boost(source_section: str, field: str):
    boosts = {
        "education": {"ugCollegeName":0.4,"pgCollegeName":0.4,"degree":0.3},
        "experience": {"workExperience":0.5},
        "skills": {"skills":0.6},
        "certifications": {"certifications":0.6},
        "summary": {"summary":0.6},
        "contact": {"email":0.5,"phoneNumber":0.5,"name":0.4}
    }
    if not source_section:
        return 0.0
    s = boosts.get(source_section.lower(),{})
    return s.get(field, 0.0)

def ner_score(nlp, txt, field):
    if not nlp or not txt:
        return 0.0
    doc = nlp(txt)
    # basic mapping
    if field=="name":
        return 0.9 if any(ent.label_=="PERSON" for ent in doc.ents) else 0.0
    if field in ("ugCollegeName","pgCollegeName"):
        return 0.9 if any(ent.label_ in ("ORG","GPE") and UNIV_HINT.search(ent.text.lower() or "") for ent in doc.ents) else 0.0
    if field=="workExperience":
        return 0.6 if any(ent.label_ in ("ORG","PERSON") for ent in doc.ents) else 0.0
    return 0.0

# ---------- pick best candidate ----------
def score_candidate(candidate: Dict[str,Any], field: str, nlp=None, embed_proto=None):
    text = clean_line(candidate.get("text",""))
    src = candidate.get("source","")
    # base signals
    s_regex = regex_score(text, field)
    s_len = length_penalty(text)
    s_section = section_boost(src, field)
    s_ner = ner_score(nlp, text, field) if nlp else 0.0
    s_embed = 0.0
    if _USE_EMBED and embed_proto and text:
        te = embed_text(text)
        if te is not None:
            # compare to multiple prototypes and take max
            s_embed = max((cos_sim(te, p) for p in embed_proto), default=0.0)
    # conflict penalty: contains verbs like "apply", "responsible" for short fields
    conflict = 0.0
    if field in ("ugCollegeName","pgCollegeName","degree") and re.search(r"\b(apply|responsible|experience|present|pursuing|seeking)\b", text, re.I):
        conflict = -0.3
    # compose weights (tuneable per field)
    weights = {
        "name": (0.4,0.2,0.2,0.2,0.0),
        "ugCollegeName": (0.15,0.25,0.35,0.15,0.10),
        "pgCollegeName": (0.15,0.25,0.35,0.15,0.10),
        "degree": (0.1,0.3,0.3,0.15,0.15),
        "certifications": (0.1,0.3,0.2,0.1,0.3),
        "workExperience": (0.1,0.3,0.4,0.15,0.05),
        "skills": (0.05,0.6,0.1,0.0,0.25),
        "summary": (0.05,0.4,0.1,0.0,0.45),
        "email": (1,0,0,0,0),
        "phoneNumber": (1,0,0,0,0)
    }
    w = weights.get(field, (0.2,0.3,0.2,0.1,0.2))
    # order: (regex, length, section, ner, embed)
    score = w[0]*s_regex + w[1]*s_len + w[2]*s_section + w[3]*s_ner + w[4]*s_embed + conflict
    # clamp
    score = max(0.0, min(1.0, score))
    return score

def pick_best(field: str, candidates: List[Dict[str,Any]], nlp=None, embed_proto=None):
    best = None
    best_score = 0.0
    reasons = {}
    for c in candidates:
        s = score_candidate(c, field, nlp=nlp, embed_proto=embed_proto)
        if s > best_score:
            best_score = s
            best = c
    return best, best_score

# ---- robust year extractor (no capturing-group pitfalls) ----
def _extract_years_from_line(ln: str) -> (str, str):
    # returns (startYear, endYear) as strings, empty if not found
    if not ln:
        return "", ""
    yrs = re.findall(r"(?:19|20)\d{2}", ln)
    if yrs:
        start = yrs[0]
        end = ""
        if len(yrs) > 1:
            end = yrs[1]
        else:
            if re.search(r"\b(present|ongoing|to date|current)\b", ln, re.I):
                end = "Present"
        return start, end
    # month-year pattern
    m = re.search(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s*(?:19|20)\d{2}).*?(present|ongoing|(?:19|20)\d{2})?", ln, re.I)
    if m:
        s = re.search(r"(?:19|20)\d{2}", m.group(1))
        start = s.group(0) if s else ""
        if m.group(2):
            if re.search(r"(?:19|20)\d{2}", m.group(2)):
                end = re.search(r"(?:19|20)\d{2}", m.group(2)).group(0)
            else:
                end = "Present"
        else:
            end = ""
        return start, end
    return "", ""

# ---- robust experience parser using _extract_years_from_line ----
def parse_experience_blocks(canonical_sections: Dict[str,str]) -> List[Dict[str,Any]]:
    out = []
    exp_text = canonical_sections.get("experience") or canonical_sections.get("work") or ""
    if not exp_text:
        exp_text = "\n\n".join([t for k,t in canonical_sections.items() if t])
    lines = split_lines(exp_text)
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        # prefer lines that contain a year or month-year pattern
        if re.search(r"(?:19|20)\d{2}", line) or re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", line, re.I):
            # extract years from this line
            startYear, endYear = _extract_years_from_line(line)
            # find company/title by scanning backwards for up to 5 lines that are not date-lines
            company = ""
            title = ""
            for back in range(1,6):
                idx = i - back
                if idx < 0:
                    break
                cand = lines[idx].strip()
                if not cand:
                    continue
                # skip date-like lines
                if re.search(r"(?:19|20)\d{2}", cand) or re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", cand, re.I):
                    continue
                # prefer ORG_HINT or TitleCase short line as company
                if not company and (ORG_HINT.search(cand.lower()) or (len(cand.split()) <= 6 and cand == cand.title())):
                    company = cand
                    continue
                # next plausible title
                if not title and (len(cand.split()) <= 8 and cand == cand.title()) and cand != company:
                    title = cand
            # collect details forward until next date-like line or next plausible company/title
            details = []
            j = i + 1
            while j < n and not re.search(r"(?:19|20)\d{2}", lines[j]) and not (ORG_HINT.search(lines[j].lower()) and len(lines[j].split())<=6):
                ln = lines[j]
                if len(ln.split()) > 2:
                    details.append(ln)
                j += 1
            # final fix: if startYear empty but details contain years, try to find them
            if not startYear:
                for d in details:
                    s,e = _extract_years_from_line(d)
                    if s:
                        startYear = s
                        if e:
                            endYear = e
                        break
            out.append({
                "organization": company or "",
                "title": title or "",
                "startYear": startYear or "",
                "endYear": endYear or "",
                "details": details
            })
            i = j
            continue
        i += 1
    return out




# ---------- skills synthesizer ----------
# ---------- improved skills synthesizer ----------
import itertools

TECH_TOKEN_RE = re.compile(r"[A-Za-z0-9\+\.\-#_/&\s]{1,80}")

def _looks_like_sentence(s: str) -> bool:
    # if contains common verbs or is long, treat as sentence
    if not s:
        return True
    if len(s.split()) > 6:
        return True
    if re.search(r"\b(developed|designed|experience|responsible|worked|involved|performed|provides|providing|using|using|implement|implementing|created|managed)\b", s, re.I):
        return True
    # contains multiple clauses/punctuation
    if any(p in s for p in [".", ";", ":"]) and len(s.split())>3:
        return True
    return False

def _is_location_or_company_like(s: str) -> bool:
    if not s:
        return True
    if re.search(r"\b(city|town|county|state|province|inc|ltd|llc|co\.|group|company|corporation|bank|university|college)\b", s, re.I):
        return True
    # short tokens that are uppercase with numbers like 'NY' or state names
    if re.fullmatch(r"[A-Z]{2,3}", s.strip()):
        return True
    # lines ending with state/country (e.g., ', Texas')
    if re.search(r",\s*[A-Za-z]{2,}$", s):
        return True
    return False

def _clean_skill_token(tok: str) -> str:
    t = tok.strip().strip(" .;:-")
    # normalize common spacing and remove trailing words like 'tools' etc.
    t = re.sub(r"\s{2,}", " ", t)
    # remove phrases that are obviously not tech (e.g., 'Experience in', 'Worked with')
    t = re.sub(r"^(experience in|worked with|expertise in|knowledge of)\s+", "", t, flags=re.I)
    return t
"""
    Improved skills synthesizer:
    - splits environment/technology lines into tokens
    - filters out location/company/sentences
    - prefers short tech phrases (<=4 words)
    - dedupes and sorts
    """
# ---------- improved skills synthesizer v2 (keyword + frequency) ----------
# ---------- skill classification helper ----------
from typing import List, Dict

def classify_skills(skills: List[str]) -> Dict[str, List[str]]:
    """
    C-2: Strict, deterministic skill categorization.
    Input: clean skill list from extract_skills()
    Output: categorized skills only (no sentences, no locations)
    """

    CATEGORIES = {
        "languages": {
            "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "SQL"
        },
        "frameworks": {
            "Spring", "Spring Boot", "Django", "Flask", "React", "Angular", "Node.js"
        },
        "databases": {
            "MySQL", "PostgreSQL", "Oracle", "MongoDB", "DB2"
        },
        "cloud": {
            "AWS", "Azure", "GCP"
        },
        "tools": {
            "Git", "GitHub", "SVN", "Docker", "Kubernetes", "Jenkins"
        },
        "testing": {
            "JUnit", "Pytest", "Selenium"
        },
        "security": {
            "Cybersecurity", "Network Security", "Ethical Hacking",
            "Penetration Testing", "Cryptography"
        }
    }

    out = {k: [] for k in CATEGORIES}
    out["other"] = []

    seen = set()

    for s in skills:
        if not s:
            continue

        key = s.strip()
        low = key.lower()

        # reject junk fragments early
        if len(key.split()) > 3:
            continue
        if re.search(r"\d{4}", key):
            continue

        placed = False
        for cat, vocab in CATEGORIES.items():
            if key in vocab:
                out[cat].append(key)
                placed = True
                break

        if not placed:
            out["other"].append(key)

    # dedupe + sort
    for k in out:
        out[k] = sorted(set(out[k]))

    # remove empty categories
    return {k: v for k, v in out.items() if v}


def extract_skills(text: str) -> list:
    """
    Noise-resistant skills extractor
    """

    if not text:
        return []

    TECH = {
        "python", "java", "javascript", "typescript", "c++", "c#", "sql",
        "html", "css", "react", "angular", "node", "node.js",
        "spring", "spring boot", "hibernate",
        "mysql", "postgresql", "oracle", "mongodb",
        "aws", "azure", "gcp", "docker", "kubernetes",
        "git", "github", "svn", "jenkins",
        "linux", "unix",
        "rest", "soap", "api",
        "junit", "pytest", "selenium",
        "cybersecurity", "network security", "ethical hacking",
        "penetration testing", "cryptography"
    }

    BAD = {
        "university", "college", "graduation", "expected",
        "profile", "summary", "experience", "education",
        "india", "texas", "missouri", "chicago", "tamil", "nadu"
    }

    skills = set()

    for chunk in re.split(r"[\n,;/•]", text):
        chunk = chunk.strip()
        if not chunk or len(chunk.split()) > 6:
            continue

        low = chunk.lower()

        if any(b in low for b in BAD):
            continue
        if re.search(r"\d{4}", chunk):
            continue
        if "@" in chunk or "http" in chunk:
            continue

        for tech in TECH:
            if tech in low:
                skills.add(tech.title())

    return sorted(skills)


def _fill_missing_work_orgs(parsed_work: List[Dict[str,Any]], canonical_sections: Dict[str,str]) -> List[Dict[str,Any]]:
    # build line index from all sections
    all_lines = []
    for sec, txt in canonical_sections.items():
        if not txt: continue
        for ln in split_lines(txt):
            all_lines.append(ln)
    # for each work item lacking organization, try to find nearest TitleCase line or ORG_HINT near any of its details or dates
    for item in parsed_work:
        if item.get("organization"):
            continue
        # search using startYear or content snippet
        candidates = []
        if item.get("startYear"):
            pattern = item.get("startYear")
            for i,ln in enumerate(all_lines):
                if pattern in ln:
                    # look back 1-4 lines
                    for back in range(1,5):
                        idx = i - back
                        if idx < 0: break
                        cand = all_lines[idx]
                        if ORG_HINT.search(cand.lower()) or (len(cand.split())<=6 and cand==cand.title()):
                            candidates.append(cand)
        # fallback: look inside details for org-like tokens
        # when iterating candidates, skip if candidate looks like a date or contains year tokens
        def _looks_like_date_line(s: str) -> bool:
            if not s:
                return False
            if YEAR_RE.search(s):
                return True
            if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", s, re.I):
                return True
            return False

        # inside _fill_missing_work_orgs where you check cand:
        if ORG_HINT.search(cand.lower()) or (len(cand.split()) <= 6 and cand == cand.title()):
            if not _looks_like_date_line(cand):
                candidates.append(cand)

        if candidates:
            item["organization"] = candidates[0]
    return parsed_work


# ---------- main builder ----------
def build_final_schema(raw_text: str, canonical_sections: Dict[str,str], nlp=None) -> Dict[str,Any]:
    t0 = time.perf_counter()
    timings = {}
    cand = collect_candidates(raw_text, canonical_sections)

    # optional prototypes (embeddings) for colleges/degrees/summary
    embed_proto = None
    if _USE_EMBED:
        prototypes = ["university", "bachelor of science", "master of science", "certificate", "skills", "work experience"]
        embed_proto = [embed_text(p) for p in prototypes if embed_text(p) is not None]

    # pick single bests
    parsed = {}
    confidences = {}

    # name
    name_best, name_score = pick_best("name", cand.get("name",[]) , nlp=nlp, embed_proto=embed_proto)
    raw_name = name_best.get("text") if name_best else ""
    parsed["name"] = _sanitize_name(raw_name)
    confidences["name"] = round(name_score * 100, 1) if parsed["name"] else 0.0

    # email/phone
    if cand.get("email"):
        parsed["email"] = cand["email"][0]["text"]
        confidences["email"] = 100.0
    else:
        parsed["email"] = ""
        confidences["email"] = 0.0
    if cand.get("phoneNumber"):
        parsed["phoneNumber"] = cand["phoneNumber"][0]["text"]
        confidences["phoneNumber"] = 100.0
    else:
        parsed["phoneNumber"] = ""
        confidences["phoneNumber"] = 0.0

    # education: structured parsing + best picks
    edu_raw = canonical_sections.get("education") or canonical_sections.get("academics") or ""
    # parse lines and detect multiple degree entries
    degrees = []
    for ln in split_lines(edu_raw):
        if DEGREE_HINT.search(ln) or UNIV_HINT.search(ln) or YEAR_RE.search(ln):
            degrees.append(ln)
    # if none, use cand degree candidates
    for d in cand.get("degree_candidates",[]):
        degrees.append(d["text"])
    # attempt to split into UG/PG by keyword or position
    ug = ""
    pg = ""
    if degrees:
        # heuristics: first degree with 'master' -> pg else ug
        for d in degrees:
            low = d.lower()
            if "master" in low or "m.sc" in low or "ms " in low or "mba" in low:
                if not pg: pg = d
            elif "bachelor" in low or "bs " in low or "b.sc" in low or "ba " in low:
                if not ug: ug = d
            else:
                # fallback assign first to ug if empty
                if not ug: ug = d
    # ----- replace existing ug/pg assignment block with this -----
    parsed["ugCollegeName"] = ug or ""
    parsed["pgCollegeName"] = pg or ""
    # ---- Demote tool lists or single tool tokens from college fields ----
    for fld in ("ugCollegeName", "pgCollegeName"):
        val = parsed.get(fld, "") or ""
        if not val:
            continue
        lowv = val.lower().strip()
        # exact single-token match or starts-with "tools:" or contains a known tool keyword
        is_tool_single = (len(lowv.split()) == 1 and lowv in TOOL_KEYWORDS)
        contains_tool_keyword = any(tok in lowv for tok in TOOL_KEYWORDS)
        starts_with_tools_label = re.match(r"^\s*(tools?:|technolog(?:ies)?:)", lowv, re.I)
        if starts_with_tools_label or is_tool_single or contains_tool_keyword:
            toks = re.split(r"[,:;|\n/]+", val)
            for t in toks:
                tt = t.strip()
                if tt:
                    parsed.setdefault("skills", [])
                    # avoid duplicates
                    if tt not in parsed["skills"]:
                        parsed["skills"].append(tt)
            parsed[fld] = ""
            confidences[fld] = 0.0

    confidences["ugCollegeName"] = round((0.9 if ug else 0.0) * 100, 1)
    confidences["pgCollegeName"] = round((0.9 if pg else 0.0) * 100, 1)

    # STRICTER: If chosen college string does NOT contain an explicit university/college hint
    # and it looks like a long narrative, demote it to summary instead of keeping as college.
    def looks_like_sentence(s):
        if not s: return False
        words = s.split()
        # contains verbs/trigger words or is too long
        if len(words) > 12:
            return True
        if re.search(r"\b(apply|pursuing|pursue|experience|strengthen|passionate|professional|currently)\b", s, re.I):
            return True
        return False

    # enforce UNIV_HINT or DEGREE_HINT or short tokenized college-like string
    for fld in ("ugCollegeName", "pgCollegeName"):
        val = parsed.get(fld, "") or ""
        if val:
            if not (UNIV_HINT.search(val.lower()) or DEGREE_HINT.search(val.lower())):
                # allow only very short names (<=5 words and TitleCase) otherwise demote
                if not (len(val.split()) <= 5 and val == val.title()):
                    # move to summary (append) and clear field
                    existing = parsed.get("summary", "") or ""
                    if existing:
                        parsed["summary"] = existing + "\n\n" + val
                    else:
                        parsed["summary"] = val
                    parsed[fld] = ""
                    confidences[fld] = 0.0

    # degrees/majors (basic)
    parsed["ugDegree"] = ""
    parsed["pgDegree"] = ""

    # Post-process degrees: if degree text looks like a narrative/profile, demote it
    for deg_field in ("ugDegree","pgDegree"):
        dval = parsed.get(deg_field,"") or ""
        if dval and looks_like_sentence(dval):
            # append to summary and clear degree
            parsed["summary"] = (parsed.get("summary","") + "\n\n" + dval).strip()
            parsed[deg_field] = ""
            confidences[deg_field] = 0.0

    if ug:
        m = re.search(r"(Bachelor|B\.A|B\.S|BSc|BS|BA|bachelor).*", ug, re.I)
        parsed["ugDegree"] = m.group(0) if m else ug
    if pg:
        m = re.search(r"(Master|M\.S|MSc|MS|MBA|master).*", pg, re.I)
        parsed["pgDegree"] = m.group(0) if m else pg

    # work experience structured
    work_blocks = parse_experience_blocks(canonical_sections)
    parsed["workExperience"] = work_blocks
    parsed["workExperience"] = _fill_missing_work_orgs(parsed["workExperience"], canonical_sections)
    confidences["workExperience"] = round(min(100, 30 + len(work_blocks)*15),1) if work_blocks else 0.0

    # certifications
    certs = []
    for c in cand.get("certifications",[]):
        certs.append(c["text"])
    parsed["certifications"] = list(dict.fromkeys([clean_line(x) for x in certs]))

    # extract skills only from SKILLS-like sections
    skills_text = (
            canonical_sections.get("skills") or
            canonical_sections.get("technical skills") or
            canonical_sections.get("technologies") or
            ""
    )

    clean_skills = extract_skills(skills_text)

    parsed["skills_by_category"] = classify_skills(clean_skills)

    # ensure no flat skills list in final JSON
    parsed.pop("skills", None)

    # confidence based on clean skills only
    confidences["skills"] = round(min(100, len(clean_skills) * 10), 1) if clean_skills else 0.0

    # summary: take top summary candidate or first paragraph from summary section
    sumcand = cand.get("summary_candidates",[])
    if canonical_sections.get("summary"):
        parsed["summary"] = canonical_sections.get("summary")
        confidences["summary"] = 100.0
    elif sumcand:
        parsed["summary"] = sumcand[0]["text"]
        confidences["summary"] = round((length_penalty(parsed["summary"])*80),1)
    else:
        parsed["summary"] = ""
        confidences["summary"] = 0.0

    # achievements (small heuristic)
    ach = []
    for sec,t in canonical_sections.items():
        if "award" in (t or "").lower() or "honor" in (t or "").lower():
            ach.extend(split_lines(t))
    parsed["achievements"] = ach

    timings["build"] = time.perf_counter() - t0
    return {
        "parsed": parsed,
        "confidence_percentage": confidences,
        "timings": timings
    }
