#!/usr/bin/env python3
"""Shared deterministic quality checks for AppNho News v1.5."""
from __future__ import annotations
import re, hashlib, difflib
from datetime import datetime, timezone
from urllib.parse import urlsplit

QUALITY_VERSION = "1.5"
# Source type alone never proves that a publisher is primary for an arbitrary claim.
# This narrow list is only a candidate hint; claim-level evidence still needs checking.
PRIMARY_TYPE_HINTS = (
    "cơ quan nhà nước", "bộ/ngành", "cổng dữ liệu", "cổng chính thức",
    "cổng thông tin chính thức", "cơ sở dữ liệu văn bản", "cơ quan thống kê",
    "ngân hàng trung ương", "cơ quan quản lý nhà nước", "liên đoàn thể thao quốc tế",
)
HIGH_RISK_TERMS = (
    # R3 is reserved for actionable/prescriptive high-stakes advice, not factual
    # reporting about wars, elections, litigation, markets or public incidents.
    "điều trị tại nhà", "phác đồ điều trị", "liều dùng khuyến nghị", "tự điều trị",
    "khuyến nghị đầu tư", "nên mua cổ phiếu", "nên bán cổ phiếu", "hãy đầu tư",
    "lợi nhuận chắc chắn", "kết luận pháp lý cho trường hợp", "tư vấn pháp luật cá nhân",
    "bạn nên kiện", "hãy ngừng thuốc", "tự ý tăng liều", "tự ý giảm liều",
)
R3_ACTIONABLE_ADVICE = (
    "bạn nên mua", "nên mua cổ phiếu", "nên bán cổ phiếu", "hãy đầu tư",
    "khuyến nghị đầu tư", "cam kết lợi nhuận", "tự điều trị", "tự ý tăng liều",
    "tự ý giảm liều", "hãy ngừng thuốc", "nên ngừng thuốc", "dùng thuốc với liều",
    "bạn nên kiện", "kết luận pháp lý cho trường hợp của bạn",
)
GENERIC_FILLER = (
    "đây là điểm quan trọng khi đánh giá",
    "độc giả cần phân biệt",
    "thông tin được công bố cần được đọc trong đúng phạm vi",
    "trong lĩnh vực này, một",
    "ở lĩnh vực này, một",
    "bản tin này là phần tóm lược",
    "độc giả quan tâm có thể theo dõi",
    "đây là thách thức phổ biến",
    "điều này có ý nghĩa thực tiễn vì",
)

def domain_key(url: str) -> str:
    try:
        host = (urlsplit(str(url)).hostname or "").lower().strip(".")
        if host.startswith("www."):
            host = host[4:]
        bits = host.split(".")
        if len(bits) >= 3 and bits[-2] in {"co", "com", "org", "gov", "ac", "edu"} and len(bits[-1]) == 2:
            return ".".join(bits[-3:])
        return ".".join(bits[-2:]) if len(bits) >= 2 else host
    except Exception:
        return ""

def is_primary_source_type(source_type: str) -> bool:
    value = (source_type or "").casefold()
    return any(hint in value for hint in PRIMARY_TYPE_HINTS)

R2_MIN_INDEPENDENT_SOURCES = 2


def classify_risk(title: str, body: list[str] | str, category: str = "") -> str:
    text = (title or "") + " " + (body if isinstance(body, str) else " ".join(body or []))
    low = text.casefold()
    if any(term in low for term in HIGH_RISK_TERMS):
        return "R3"
    if any(term in low for term in (
        "tỷ giá", "lãi suất", "giá vàng", "lạm phát", "ngân sách nhà nước", "xuất nhập khẩu",
        "đình công", "sa thải hàng loạt", "dữ liệu cá nhân", "rò rỉ dữ liệu", "an ninh mạng",
        "sự cố hệ thống", "sản phẩm lỗi", "thu hồi sản phẩm", "tăng thuế", "thuế quan",
        "đàm phán hòa bình", "lệnh trừng phạt"
    )):
        return "R2"
    return "R1"


def ttl_for_data_type(data_type: str, risk_level: str = "R1") -> int:
    """Conservative TTL policy; model-proposed TTLs cannot extend these ceilings."""
    key=(data_type or "general").casefold()
    limits={
        "breaking_news":6, "market_price":2, "fx_rate":2, "financial_market":4,
        "weather":3, "public_health":12, "law_policy":24,
        "official_statistics":72, "research_study":168, "historical":8760,
        "general":24,
    }
    ttl=limits.get(key,24)
    if risk_level=="R3": ttl=min(ttl,6)
    elif risk_level=="R2": ttl=min(ttl,12)
    return ttl


# The lower edge of each editorial target range is also the mandatory
# publication floor. This keeps the prompt, provider gate and final quality
# validator consistent; longer targets remain preferred within each range.
MINIMUM_WORDS_BY_TYPE = {
    # Validation floors are deliberately far below the writing targets below. The prompt asks
    # the model for the target length; validation only rejects a draft that is too thin to be a
    # news item at all. A short article that carries real information is acceptable.
    "quick_update": 100,
    "short_explainer": 120,
    "news_analysis": 220,
    "long_analysis": 320,
    "ai_assisted_independent_editorial": 150,
}
TARGET_WORD_RANGES_BY_TYPE = {
    "quick_update": (180, 260),
    "short_explainer": (250, 380),
    "news_analysis": (450, 650),
    "long_analysis": (650, 850),
    "ai_assisted_independent_editorial": (300, 420),
}
MINIMUM_PARAGRAPHS_BY_TYPE = {
    "quick_update": 2,
    "short_explainer": 2,
    "news_analysis": 3,
    "long_analysis": 4,
    "ai_assisted_independent_editorial": 2,
}

def minimum_words_for_type(content_type: str) -> int:
    return MINIMUM_WORDS_BY_TYPE.get(content_type or "", 120)

def target_word_range_for_type(content_type: str) -> tuple[int, int]:
    return TARGET_WORD_RANGES_BY_TYPE.get(content_type or "", (500, 650))

def minimum_paragraphs_for_type(content_type: str) -> int:
    return MINIMUM_PARAGRAPHS_BY_TYPE.get(content_type or "", 2)


def is_commercial_license(license_name: str) -> bool:
    lic=re.sub(r"\s+"," ",str(license_name or "").casefold().replace("creative commons","cc")).strip()
    if any(term in lic for term in ("nc", "noncommercial", "non-commercial", "nd", "no derivatives")):
        return False
    return lic in {"cc0", "cc0 1.0", "cc by 4.0", "cc by 3.0", "cc by 2.0",
                   "cc by-sa 4.0", "cc by-sa 3.0", "cc by-sa 2.0",
                   "public domain", "public domain mark", "pdm"}

def body_stats(body: list[str] | str) -> dict:
    paras = body if isinstance(body, list) else re.split(r"\n\s*\n", str(body or ""))
    paras = [re.sub(r"\s+", " ", str(p)).strip() for p in paras if str(p).strip()]
    norm = [re.sub(r"\W+", " ", p.casefold()).strip() for p in paras]
    words = len(re.findall(r"\S+", " ".join(paras)))
    unique_ratio = len(set(norm)) / max(1, len(norm))
    filler_hits = []
    full = " ".join(paras).casefold()
    for phrase in GENERIC_FILLER:
        if phrase in full:
            filler_hits.append(phrase)
    return {
        "paragraphs": len(paras),
        "words": words,
        "unique_paragraph_ratio": round(unique_ratio, 3),
        "filler_hits": filler_hits,
        "body_chars": sum(len(p) for p in paras),
    }

def validate_fact_ledger(fact_ledger, allowed_urls, min_claims=3, primary_urls=None):
    errors=[]
    if not isinstance(fact_ledger,list) or len(fact_ledger)<min_claims:
        return [f"fact_ledger cần ít nhất {min_claims} dữ kiện có thể kiểm tra"]
    allowed={str(x).strip() for x in allowed_urls if x}
    for i,fact in enumerate(fact_ledger,1):
        if not isinstance(fact,dict):
            errors.append(f"fact_ledger[{i}] không phải object"); continue
        claim=str(fact.get('claim') or '').strip()
        refs=fact.get('source_urls')
        snippet=str(fact.get('evidence_snippet') or '').strip()
        locator=str(fact.get('evidence_locator') or '').strip()
        if len(claim)<20: errors.append(f"fact_ledger[{i}] thiếu nội dung dữ kiện")
        if not isinstance(refs,list) or not refs:
            errors.append(f"fact_ledger[{i}] không gắn URL chứng cứ"); continue
        if any(str(u).strip() not in allowed for u in refs):
            errors.append(f"fact_ledger[{i}] chứa URL ngoài tập nguồn đã thu thập"); continue
        if len(snippet)<20 and len(locator)<8:
            errors.append(f"fact_ledger[{i}] thiếu trích đoạn chứng cứ hoặc vị trí kiểm tra")
        # Article claims are always Vietnamese; source excerpts may be in any
        # language. Cross-language support is checked against source_claim below,
        # never by comparing Vietnamese vocabulary with a foreign-language quote.
        source_claim=str(fact.get('source_claim') or '').strip()
        evidence_items=fact.get('evidence_by_source') if isinstance(fact.get('evidence_by_source'),list) else []
        evidence_snippets=[str(x.get('snippet') or '') for x in evidence_items if isinstance(x,dict)]
        candidate_snippets=[snippet]+evidence_snippets
        # source_claim is no longer required to be verbatim: articles are rewritten in the
        # editor's own words and Research has already sealed the facts. Only the evidence
        # excerpt itself must be genuine (checked against the fetched page below).
        # Do not compare Vietnamese claim vocabulary with a source-language excerpt.
        # The exact excerpt is checked against the fetched page in verify_fact_ledger_against_pages.
        # Source independence is evaluated once for the researched article as a whole.
        # A directly evidenced supporting detail need not be repeated by every publisher.
        # Core-fact safety is retained through exact source anchoring, article-level
        # independent-source requirements, and stricter R2/R3 policy.
    return errors


def normalize_evidence_text(value: str) -> str:
    """Normalize publisher text and a short quotation for robust exact-span matching."""
    text=str(value or "").casefold()
    # Preserve Unicode letters and digits; punctuation/markup become single spaces.
    text=re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()



def _claim_sentence_sequence_match(claim: str, snippet: str, threshold: float = 0.88):
    """Conservative direction/order check between a claim and the quoted source excerpt.

    Exact substring presence alone is insufficient: swapping buyer/seller or actor/object
    can preserve every token while reversing the fact. Compare claim tokens with the best
    sentence in the quote, preserving token order. Ambiguous paraphrases fail closed.
    """
    stop = {
        "và","là","của","cho","khi","trong","những","các","một","về","với","từ","theo",
        "tại","sau","trước","ngày","hôm","qua","được","đã","sẽ","đang","này","đó",
        "vào","đến","bởi","vì","như","có","không","trên","dưới","giữa","nhiều",
        "the","a","an","of","to","in","on","by","for","with","and","was","were","is"
    }
    def tokens(value):
        raw_tokens=re.findall(r"[\wÀ-ỹ]+", str(value or ""))
        out=[]
        for raw in raw_tokens:
            folded=raw.casefold()
            # Keep uppercase single-letter entity labels such as Company A / Company B.
            if (len(folded)>1 and folded not in stop) or (len(raw)==1 and raw.isupper()):
                out.append(folded)
        return out
    claim_tokens=tokens(claim)
    if len(claim_tokens)<4:
        return False, 0.0
    # Catch opposite polarity/direction even when almost every other token matches.
    opposite_pairs=(
        ("tăng","giảm"),("tăng trưởng","suy giảm"),("mua","bán"),
        ("lãi","lỗ"),("lợi nhuận","thua lỗ"),("thắng","thua"),
        ("mở","đóng"),("cao hơn","thấp hơn"),("chấp thuận","từ chối"),
        ("thông qua","bác bỏ"),("ủng hộ","phản đối")
    )
    claim_norm=normalize_evidence_text(claim)
    snippet_norm=normalize_evidence_text(snippet)
    for left,right in opposite_pairs:
        claim_has_left=left in claim_norm
        claim_has_right=right in claim_norm
        source_has_left=left in snippet_norm
        source_has_right=right in snippet_norm
        if (claim_has_left and source_has_right and not claim_has_right) or (claim_has_right and source_has_left and not claim_has_left):
            return False,0.0
    sentences=[x.strip() for x in re.split(r"(?<=[.!?;])\s+|\n+", str(snippet or "")) if x.strip()]
    if not sentences:
        sentences=[snippet]
    best=0.0
    for sentence in sentences:
        source_tokens=tokens(sentence)
        if not source_tokens:
            continue
        # Compare to bounded windows so surrounding context does not dilute the score.
        windows=[source_tokens]
        for width in (len(claim_tokens), max(4,len(claim_tokens)-2), len(claim_tokens)+2):
            if width<=0 or width>len(source_tokens):
                continue
            windows.extend(source_tokens[i:i+width] for i in range(len(source_tokens)-width+1))
        for window in windows:
            score=difflib.SequenceMatcher(None,claim_tokens,window,autojunk=False).ratio()
            if score>best:
                best=score
    return best>=threshold,best

def repair_fact_ledger_anchors(fact_ledger, allowed_urls, evidence_pages):
    """Normalize AI evidence anchors to exact Research-fetched excerpts.

    This repairs a formatting/field-mapping error only: source_claim is reset to an
    already supplied verbatim excerpt that is confirmed in the matching fetched page.
    It never invents or rewrites an excerpt and never adds a source URL.
    """
    allowed={str(x).strip() for x in (allowed_urls or []) if x}
    pages={str(url).strip():normalize_evidence_text(page)
           for url,page in (evidence_pages or {}).items() if str(url).strip() in allowed}
    repaired=[]
    for original in fact_ledger if isinstance(fact_ledger,list) else []:
        if not isinstance(original,dict):
            repaired.append(original); continue
        fact=dict(original)
        candidates=[]
        raw=fact.get('evidence_by_source')
        if isinstance(raw,list):
            for item in raw:
                if not isinstance(item,dict): continue
                url=str(item.get('source_url') or '').strip()
                snippet=str(item.get('snippet') or item.get('evidence_snippet') or '').strip()
                norm=normalize_evidence_text(snippet)
                if url in pages and norm and norm in pages[url]:
                    candidates.append({'source_url':url,'snippet':snippet,
                                       'locator':str(item.get('locator') or item.get('evidence_locator') or '')})
        if not candidates:
            snippet=str(fact.get('evidence_snippet') or '').strip()
            norm=normalize_evidence_text(snippet)
            if norm:
                for url in fact.get('source_urls') or []:
                    url=str(url).strip()
                    if url in pages and norm in pages[url]:
                        candidates.append({'source_url':url,'snippet':snippet,
                                           'locator':str(fact.get('evidence_locator') or '')})
        if candidates:
            anchor=normalize_evidence_text(fact.get('source_claim') or '')
            def _tokens(text):
                return set(re.findall(r"\w+",normalize_evidence_text(text).casefold()))
            if not anchor:
                # Optional field omitted: the verified excerpt is its anchor.
                fact['source_claim']=candidates[0]['snippet']
            elif not any(anchor in normalize_evidence_text(c['snippet']) for c in candidates):
                # The quote is not contiguous in any verified excerpt. Re-anchor ONLY when every
                # word of it occurs in that excerpt (trimmed/ellipsized/reflowed quote). A quote
                # containing a word the source does not have may be an altered fact
                # ("announced" -> "cancelled") and stays unchanged so the draft is corrected.
                words=_tokens(anchor)
                for c in candidates:
                    if words and words <= _tokens(c['snippet']):
                        fact['source_claim']=c['snippet']
                        break
            fact['evidence_by_source']=candidates
            fact['evidence_snippet']=candidates[0]['snippet']
            fact['evidence_locator']=candidates[0]['locator']
            fact['source_urls']=list(dict.fromkeys(
                [str(x).strip() for x in fact.get('source_urls',[]) if str(x).strip() in allowed]
                +[x['source_url'] for x in candidates]
            ))
        repaired.append(fact)
    return repaired


def verify_fact_ledger_against_pages(fact_ledger, allowed_urls, evidence_pages,
                                     min_claims=3, primary_urls=None,
                                     source_families=None, verified_at=None):
    """Verify verbatim evidence against fetched pages, including claim-level corroboration.

    Core facts need either an exact excerpt from a primary source or exact excerpts
    from two independent source families. Supporting facts need at least one source.
    """
    errors=validate_fact_ledger(
        fact_ledger, allowed_urls, min_claims=min_claims, primary_urls=primary_urls
    )
    if errors:
        return errors, fact_ledger
    if not isinstance(evidence_pages, dict) or not evidence_pages:
        return ["Không có văn bản nguồn thực tế để đối chiếu fact ledger"], fact_ledger

    allowed={str(x).strip() for x in allowed_urls if x}
    primary={str(x).strip() for x in (primary_urls or [])}
    families=source_families or {}
    normalized_pages={}
    for url, page in evidence_pages.items():
        url=str(url).strip()
        normalized=normalize_evidence_text(page)
        if url in allowed and normalized:
            normalized_pages[url]={
                "text":normalized,
                "sha256":hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            }

    enriched=[]
    stamp=verified_at or datetime.now(timezone.utc).isoformat()
    for i, original in enumerate(fact_ledger, 1):
        fact=dict(original)
        claim=str(fact.get("claim") or "").strip()
        claim_numbers=set(re.findall(r"\d+(?:[.,]\d+)?", claim))
        claim_terms={x for x in re.findall(r"[\wÀ-ỹ]{4,}", claim.casefold())}
        raw_evidence=fact.get("evidence_by_source")
        evidence_items=[]
        if isinstance(raw_evidence,list) and raw_evidence:
            for item in raw_evidence:
                if isinstance(item,dict):
                    evidence_items.append({
                        "source_url":str(item.get("source_url") or "").strip(),
                        "snippet":str(item.get("snippet") or item.get("evidence_snippet") or "").strip(),
                        "locator":str(item.get("locator") or item.get("evidence_locator") or "").strip()
                    })
        else:
            # Backward-compatible single excerpt: it is verified against every cited page,
            # but core-fact corroboration still requires two actual matches or one primary.
            evidence_items=[{
                "source_url":str(url).strip(),
                "snippet":str(fact.get("evidence_snippet") or "").strip(),
                "locator":str(fact.get("evidence_locator") or "").strip()
            } for url in (fact.get("source_urls") or [])]

        verified_items=[]
        for item in evidence_items:
            url=item["source_url"]
            snippet=item["snippet"]
            snippet_norm=normalize_evidence_text(snippet)
            if url not in allowed or url not in [str(x).strip() for x in (fact.get("source_urls") or [])]:
                continue
            page=normalized_pages.get(url)
            if not page or len(snippet_norm)<20 or snippet_norm not in page["text"]:
                continue
            # The excerpt is the immutable evidence anchor. Research has already sealed the facts, so
            # the claim's wording is not compared with the excerpt (a Vietnamese rewrite never matches
            # an English sentence word for word). A figure in the claim must still exist on the page;
            # localized dates are not compared.
            raw_page=str((evidence_pages or {}).get(url) or "")
            if not numbers_supported(claim,raw_page):
                continue
            family=str(families.get(url) or domain_key(url)).casefold()
            verified_items.append({
                "source_url":url,
                "snippet":snippet,
                "locator":item["locator"],
                "family":family,
                "page_sha256":page["sha256"],
                "snippet_sha256":hashlib.sha256(snippet_norm.encode("utf-8")).hexdigest(),
                "verified_at":stamp,
                "match_method":"exact_normalized_substring"
            })

        # Deduplicate multiple excerpts from the same publisher family.
        unique={}
        for item in verified_items:
            unique.setdefault(item["family"],item)
        verified_items=list(unique.values())
        importance=str(fact.get("importance") or "supporting").casefold()
        verified_primary=any(item["source_url"] in primary for item in verified_items)
        if not verified_items:
            errors.append(
                f"fact_ledger[{i}] không có trích đoạn nguyên văn tồn tại trên trang nguồn hoặc có số liệu không có trong nguồn"
            )
            enriched.append(fact)
            continue
        # Corroboration is a property of the researched story, not a requirement
        # that every individual detail be repeated verbatim by two publishers.
        # At least one exact, fetched-page excerpt is mandatory for every ledger fact.

        # Keep a convenient top-level excerpt for rendering and older consumers.
        fact["evidence_snippet"]=verified_items[0]["snippet"]
        fact["evidence_locator"]=verified_items[0]["locator"]
        fact["evidence_by_source"]=[
            {"source_url":x["source_url"],"snippet":x["snippet"],"locator":x["locator"]}
            for x in verified_items
        ]
        fact["evidence_verifications"]=[
            {k:x[k] for k in ("source_url","page_sha256","snippet_sha256","verified_at","match_method")}
            for x in verified_items
        ]
        enriched.append(fact)
    return errors, enriched


def validate_fact_ledger_proof(fact_ledger, allowed_urls, min_claims=3,
                               primary_urls=None, source_families=None):
    """Validate persisted evidence proof and claim-level independent corroboration."""
    errors=validate_fact_ledger(
        fact_ledger, allowed_urls, min_claims=min_claims, primary_urls=primary_urls
    )
    if errors:
        return errors
    allowed={str(x).strip() for x in allowed_urls if x}
    primary={str(x).strip() for x in (primary_urls or [])}
    families=source_families or {}
    for i, fact in enumerate(fact_ledger, 1):
        evidence=fact.get("evidence_by_source") if isinstance(fact,dict) else None
        proofs=fact.get("evidence_verifications") if isinstance(fact,dict) else None
        if not isinstance(evidence,list) or not evidence or not isinstance(proofs,list) or not proofs:
            errors.append(f"fact_ledger[{i}] thiếu danh sách trích đoạn và xác minh theo từng nguồn")
            continue
        proof_map={str(x.get("source_url") or "").strip():x for x in proofs if isinstance(x,dict)}
        primary_excerpt=normalize_evidence_text(fact.get("evidence_snippet") or "")
        first_excerpt=normalize_evidence_text(evidence[0].get("snippet") or "") if isinstance(evidence[0],dict) else ""
        if not primary_excerpt or primary_excerpt!=first_excerpt:
            errors.append(f"fact_ledger[{i}] trích đoạn chính không khớp danh sách chứng cứ đã xác minh")
        verified_families=set()
        verified_primary=False
        for item in evidence:
            if not isinstance(item,dict):
                continue
            url=str(item.get("source_url") or "").strip()
            snippet_norm=normalize_evidence_text(item.get("snippet") or "")
            proof=proof_map.get(url)
            if url not in allowed or url not in [str(x).strip() for x in fact.get("source_urls",[])]:
                errors.append(f"fact_ledger[{i}] chứng cứ gắn với URL ngoài tập nguồn")
                continue
            if not isinstance(proof,dict) or proof.get("match_method")!="exact_normalized_substring":
                errors.append(f"fact_ledger[{i}] thiếu xác minh nguyên văn cho {domain_key(url)}")
                continue
            if proof.get("snippet_sha256") != hashlib.sha256(snippet_norm.encode("utf-8")).hexdigest():
                errors.append(f"fact_ledger[{i}] trích đoạn đã thay đổi sau khi xác minh")
                continue
            if not re.fullmatch(r"[a-f0-9]{64}",str(proof.get("page_sha256") or "")):
                errors.append(f"fact_ledger[{i}] thiếu hash văn bản nguồn")
                continue
            try:
                datetime.fromisoformat(str(proof.get("verified_at") or "").replace("Z","+00:00"))
            except Exception:
                errors.append(f"fact_ledger[{i}] thiếu thời điểm xác minh")
                continue
            family=str(families.get(url) or domain_key(url)).casefold()
            verified_families.add(family)
            verified_primary=verified_primary or url in primary
        if not verified_families:
            errors.append(f"fact_ledger[{i}] không còn chứng cứ nguồn đã xác minh ở bước xuất bản")
    return errors


NUMBER_RE=re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(text):
    return set(NUMBER_RE.findall(str(text or "")))


def _num_key(token):
    """1.200 / 1,200 / 1 200 all compare equal; decimals are rare enough in news to accept this."""
    return re.sub(r"[.,]","",str(token))


VN_DATE_RE=re.compile(
    r"(?i)(?:\bngày\s+)?\b\d{1,2}\s*(?:/|-|tháng)\s*\d{1,2}(?:\s*(?:/|-|năm)\s*\d{2,4})?\b|\btháng\s+\d{1,2}\b|\bngày\s+\d{1,2}\b")


def strip_localized_dates(text):
    """Dates are localized ("31 October" -> "31 tháng 10"); they are not compared numerically."""
    return VN_DATE_RE.sub(" ",str(text or ""))


def numbers_supported(text, source_text):
    """True when every figure in text (dates aside) also appears in source_text."""
    have={_num_key(x) for x in numbers_in(source_text)}
    return all(_num_key(x) in have for x in numbers_in(strip_localized_dates(text)))


def _ledger_evidence_text(fact_ledger):
    """Claims plus the verbatim excerpts that were hash-verified against the source pages."""
    parts=[]
    for item in (fact_ledger or []):
        if not isinstance(item,dict):
            continue
        parts.append(str(item.get("claim") or ""))
        parts.append(str(item.get("source_claim") or ""))
        parts.append(str(item.get("evidence_snippet") or ""))
        for ev in item.get("evidence_by_source") or []:
            if isinstance(ev,dict):
                parts.append(str(ev.get("snippet") or ""))
    return " ".join(parts)


def compute_verified_numbers(body, fact_ledger, evidence_pages):
    """Numbers used in the body that are supported by the ledger or the sealed source pages.

    Computed at writing time (when the source pages are available) and stored on the
    article, so later audits/publication, which no longer hold the pages, apply the same
    rule instead of a stricter ledger-only rule that rejected correct figures such as
    "12 tháng".
    """
    paragraphs=body if isinstance(body,list) else re.split(r"\n\s*\n",str(body or ""))
    allowed=numbers_in(_ledger_evidence_text(fact_ledger))
    allowed|=numbers_in(" ".join(str(x or "") for x in (evidence_pages or {}).values()))
    used=set()
    for paragraph in paragraphs:
        used|=numbers_in(strip_localized_dates(re.sub(r"(?i)\bđoạn\s+\d+\b"," ",str(paragraph or ""))))
    allowed_keys={_num_key(x) for x in allowed}
    return sorted(x for x in used if _num_key(x) in allowed_keys)


def validate_body_fact_coverage(body, fact_ledger, evidence_pages=None, verified_numbers=None):
    """Reject numeric facts absent from the ledger, its verified excerpts, or the source pages."""
    paragraphs=body if isinstance(body,list) else re.split(r"\n\s*\n",str(body or ""))
    allowed=numbers_in(_ledger_evidence_text(fact_ledger))
    # A number can be accurately supported by a fetched source even when the AI did not
    # repeat it in a ledger claim, so also accept the sealed source pages when available
    # and the numbers recorded at writing time (verified against those pages).
    allowed|=numbers_in(" ".join(str(x or "") for x in (evidence_pages or {}).values()))
    allowed|={str(x) for x in (verified_numbers or [])}
    allowed_keys={_num_key(x) for x in allowed}
    errors=[]
    for idx, paragraph in enumerate(paragraphs,1):
        # Ignore editorial paragraph labels such as "Đoạn 1" and localized dates.
        numeric_text=strip_localized_dates(re.sub(r"(?i)\bđoạn\s+\d+\b"," ",str(paragraph or "")))
        missing=sorted(x for x in numbers_in(numeric_text) if _num_key(x) not in allowed_keys)
        if missing:
            errors.append(
                f"Đoạn {idx} có số liệu/ngày tháng không tìm thấy trong fact ledger hoặc văn bản nguồn: {', '.join(missing[:6])}"
            )
    return errors

def validate_article_quality(article: dict, min_words=None, min_paragraphs=None, evidence_pages=None):
    errors = []
    title = str(article.get("title") or "").strip()
    summary = str(article.get("summary") or "").strip()
    body = article.get("body") or []
    stats = body_stats(body)
    if article.get("fact_ledger"):
        errors.extend(validate_body_fact_coverage(body, article.get("fact_ledger") or [], evidence_pages=evidence_pages,
                                                  verified_numbers=article.get("verified_numbers")))
    content_type = article.get('content_type') or "short_explainer"
    required_words = minimum_words_for_type(content_type) if min_words is None else min_words
    required_paragraphs = minimum_paragraphs_for_type(content_type) if min_paragraphs is None else min_paragraphs
    if len(title) < 12:
        errors.append("Tiêu đề quá ngắn hoặc thiếu")
    if len(summary) < 45:
        errors.append("Sapo/tóm tắt quá ngắn")
    if stats["words"] < required_words:
        errors.append(f"Nội dung chỉ có {stats['words']} từ; cần ít nhất {required_words} theo thể loại")
    if stats["paragraphs"] < required_paragraphs:
        errors.append(f"Nội dung chỉ có {stats['paragraphs']} đoạn; cần ít nhất {required_paragraphs}")
    if stats["unique_paragraph_ratio"] < 0.85:
        errors.append("Có đoạn lặp hoặc gần trùng")
    # A small absolute floor catches empty/placeholder text without imposing
    # another genre-based length test on top of the word and paragraph checks.
    if stats["body_chars"] < 450:
        errors.append("Nội dung quá ngắn để truyền tải một thông tin hoàn chỉnh")
    if stats["filler_hits"]:
        errors.append("Có câu/đoạn khuôn mẫu chung chung: " + "; ".join(stats["filler_hits"][:3]))
    editorial_value=str(article.get("editorial_value") or "").strip()
    editorial_parts=[x.strip() for x in re.split(r"[.;!?\n]|(?i:\bđồng thời\b|\bngoài ra\b|\bbên cạnh đó\b)",editorial_value) if x and len(x.strip())>=18]
    if len(editorial_parts)<2 or len(set(x.casefold() for x in editorial_parts))<2:
        errors.append("Đóng góp biên tập phải nêu ít nhất hai nội dung cụ thể, không chỉ là một câu khẩu hiệu")
    if article.get("risk_level") not in {"R1", "R2", "R3"}:
        errors.append("Thiếu hoặc sai phân loại rủi ro")
    return errors, stats

def source_independence(source_references):
    families=set(); primary=False; domains=set()
    for ref in source_references or []:
        if not isinstance(ref,dict): continue
        domain=domain_key(ref.get('url',''))
        if domain: domains.add(domain)
        family=str(ref.get('source_family') or domain).strip().casefold()
        if family: families.add(family)
        primary=primary or bool(ref.get('is_primary_for_claim'))
    return len(families),primary,sorted(families)


def validate_r3_content(title: str, body: list[str] | str):
    text=(title or "")+" "+(body if isinstance(body,str) else " ".join(body or []))
    low=text.casefold()
    return [term for term in R3_ACTIONABLE_ADVICE if term in low]


_TITLE_STOPWORDS = {
    "và","là","của","cho","khi","trong","những","các","một","về","với","từ","theo",
    "tại","sau","trước","ngày","hôm","qua","được","đã","sẽ","đang","này","đó","nào",
    "ra","vào","đến","bởi","vì","như","có","không","trên","dưới","giữa","nhiều","mới",
    "a","an","the","and","or","but","if","then","than","as","at","by","for","from","in","into",
    "of","on","out","over","to","up","with","after","before","during","amid","ahead","back",
    "still","just","also","test","tests","drop","drops","rise","rises","new","latest","report",
}

def evidence_matches_title(title: str, evidence: str, minimum_overlap=0.30) -> bool:
    title_tokens={x for x in re.findall(r"[a-z0-9À-ỹ]+",str(title or "").casefold()) if len(x)>2 and x not in _TITLE_STOPWORDS}
    if len(title_tokens)<2:
        return False
    evidence_tokens=set(re.findall(r"[a-z0-9À-ỹ]+",str(evidence or "")[:5000].casefold()))
    overlap=len(title_tokens & evidence_tokens)/len(title_tokens)
    return overlap>=minimum_overlap


def ready_candidate_errors(article):
    """The exact checks a READY candidate must pass in audit_site.py and publish_ready.py.

    Writing runs this before a draft can become READY, so an article can never be queued
    that the next audit would reject (which used to block every later workflow run).
    """
    errors=[]
    if not isinstance(article,dict) or not article.get("id"):
        return ["READY candidate has no article ID"]
    quality,_=validate_article_quality(article)
    errors.extend(quality)
    refs=[x for x in (article.get("source_references") or []) if isinstance(x,dict)]
    urls=[x.get("url") for x in refs]
    primary_urls=[x.get("url") for x in refs if x.get("is_primary_for_claim")]
    families={str(x.get("url") or "").strip():x.get("source_family") or domain_key(x.get("url","")) for x in refs}
    errors.extend(validate_fact_ledger_proof(article.get("fact_ledger"),urls,min_claims=3,
                                             primary_urls=primary_urls,source_families=families))
    count,primary,_=source_independence(refs)
    if count<2 and not primary:
        errors.append("Không đủ hai miền nguồn độc lập hoặc nguồn chính thức")
    risk=article.get("risk_level")
    if risk=="R2" and not primary and count<R2_MIN_INDEPENDENT_SOURCES:
        errors.append("R2 thiếu nguồn chính thức hoặc hai miền nguồn độc lập")
    if risk=="R3" and not primary:
        errors.append("R3 không có nguồn chính thức")
    return errors


def _claim_unit_score(claim, unit_text, preferred_urls, unit_urls):
    """Loose topical match between a (Vietnamese) claim and a source-language fact unit."""
    claim_numbers={_num_key(x) for x in numbers_in(strip_localized_dates(claim))}
    unit_numbers={_num_key(x) for x in numbers_in(unit_text)}
    score=3*len(claim_numbers & unit_numbers)
    unit_low=str(unit_text or "").casefold()
    for token in set(re.findall(r"[\wÀ-ỹ]{4,}", str(claim or "").casefold())):
        if token in unit_low:
            score+=1
    if set(preferred_urls or []) & set(unit_urls or []):
        score+=2
    return score


def complete_fact_ledger(model_ledger, fact_units, evidence_pages, allowed_urls,
                         primary_urls=None, minimum=3):
    """Build the ledger from the sealed Research fact units; the model's own is advisory.

    Research already fetched the pages and extracted the fact units. The writer only has to
    say, in its own words, which facts it used. Each claim is attached to the most relevant
    Research excerpt (verbatim on the fetched page), and the ledger is topped up from unused
    Research units so it always reaches `minimum`. No excerpt is invented or rewritten.
    """
    allowed={str(x).strip() for x in (allowed_urls or []) if x}
    primary={str(x).strip() for x in (primary_urls or [])}
    pages={str(u).strip():normalize_evidence_text(t) for u,t in (evidence_pages or {}).items()
           if str(u).strip() in allowed}
    units=[]
    for unit in fact_units or []:
        if not isinstance(unit,dict):
            continue
        text=str(unit.get("text") or "").strip()
        norm=normalize_evidence_text(text)
        urls=[str(u).strip() for u in (unit.get("source_urls") or unit.get("urls") or [])]
        good=[u for u in urls if u in pages and len(norm)>=20 and norm in pages[u]]
        if good:
            units.append({"text":text,"urls":good})
    used=set()

    def attach(fact, index):
        unit=units[index]
        used.add(index)
        fact["source_urls"]=list(unit["urls"])
        fact["evidence_snippet"]=unit["text"]
        fact["evidence_locator"]="Hồ sơ Research (dữ kiện đã trích từ trang nguồn)"
        fact["evidence_by_source"]=[{"source_url":u,"snippet":unit["text"],
                                      "locator":fact["evidence_locator"]} for u in unit["urls"]]
        if any(u in primary for u in unit["urls"]):
            fact["importance"]="core"
        fact.pop("source_claim",None)
        fact.setdefault("importance","supporting")

    result=[]
    for original in model_ledger if isinstance(model_ledger,list) else []:
        if not isinstance(original,dict):
            continue
        fact=dict(original)
        claim=str(fact.get("claim") or "").strip()
        if len(claim)<20:
            continue
        fact.pop("source_claim",None)
        own_ok=False
        for item in fact.get("evidence_by_source") or []:
            if isinstance(item,dict):
                url=str(item.get("source_url") or "").strip()
                norm=normalize_evidence_text(item.get("snippet") or "")
                if url in pages and len(norm)>=20 and norm in pages[url]:
                    own_ok=True
        if own_ok:
            fact["evidence_by_source"]=[x for x in fact["evidence_by_source"] if isinstance(x,dict)
                and str(x.get("source_url") or "").strip() in pages
                and normalize_evidence_text(x.get("snippet") or "") in pages[str(x.get("source_url") or "").strip()]
                and len(normalize_evidence_text(x.get("snippet") or ""))>=20]
            fact["source_urls"]=list(dict.fromkeys(str(x["source_url"]).strip() for x in fact["evidence_by_source"]))
            fact["evidence_snippet"]=fact["evidence_by_source"][0]["snippet"]
            fact["evidence_locator"]=str(fact["evidence_by_source"][0].get("locator") or "Hồ sơ Research")
            result.append(fact)
            continue
        preferred=[str(u).strip() for u in (fact.get("source_urls") or [])]
        scored=sorted(((_claim_unit_score(claim,u["text"],preferred,u["urls"])-(0 if i not in used else 100),i)
                       for i,u in enumerate(units)),reverse=True)
        if scored:
            attach(fact,scored[0][1])
            result.append(fact)
    # Top up from Research units not yet used so the ledger always has enough facts.
    ranked=sorted((i for i in range(len(units)) if i not in used),
                  key=lambda i:(-(len(re.findall(r"\d",units[i]["text"]))>0),-len(units[i]["urls"]),i))
    for i in ranked:
        if len(result)>=minimum:
            break
        fact={"claim":"Nguồn ghi nhận: "+units[i]["text"][:260],"importance":"supporting"}
        attach(fact,i)
        result.append(fact)
    return result
