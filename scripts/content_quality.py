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
    "điều trị", "phác đồ", "liều dùng", "chẩn đoán", "tự điều trị", "thuốc",
    "khuyến nghị đầu tư", "nên mua cổ phiếu", "nên bán cổ phiếu", "chứng khoán",
    "lợi nhuận chắc chắn", "kết luận pháp lý", "tư vấn pháp luật", "khởi kiện",
    "cáo buộc", "bị kết tội", "an toàn tính mạng", "sơ tán", "thiên tai",
    "bạo lực", "xâm hại", "trẻ em", "dịch bệnh", "dịch tễ", "ngộ độc",
    "tai nạn", "chiến sự", "tấn công", "khủng bố", "bầu cử", "tranh chấp",
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

def classify_risk(title: str, body: list[str] | str, category: str = "") -> str:
    text = (title or "") + " " + (body if isinstance(body, str) else " ".join(body or []))
    low = text.casefold()
    if any(term in low for term in HIGH_RISK_TERMS):
        return "R3"
    if any(term in low for term in (
        "tỷ giá", "lãi suất", "giá vàng", "lạm phát", "chính sách", "doanh nghiệp",
        "thị trường", "ngân sách", "xuất nhập khẩu", "thuế", "quy định", "luật",
        "đình công", "sa thải", "dữ liệu cá nhân", "an ninh mạng", "sự cố hệ thống",
        "xung đột", "đàm phán", "sản phẩm lỗi", "thu hồi sản phẩm"
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


# Generation targets are editorial aspirations, not pass/fail limits.
# The minimum is a safety floor only; evidence, factual accuracy and editorial value
# remain the actual publication criteria.
MINIMUM_WORDS_BY_TYPE = {
    "quick_update": 120,
    "short_explainer": 220,
    "news_analysis": 420,
    "long_analysis": 550,
    "ai_assisted_independent_editorial": 220,
}
TARGET_WORD_RANGES_BY_TYPE = {
    "quick_update": (250, 350),
    "short_explainer": (500, 650),
    "news_analysis": (800, 1000),
    "long_analysis": (1000, 1300),
    "ai_assisted_independent_editorial": (500, 650),
}
MINIMUM_PARAGRAPHS_BY_TYPE = {
    "quick_update": 2,
    "short_explainer": 3,
    "news_analysis": 4,
    "long_analysis": 5,
    "ai_assisted_independent_editorial": 3,
}

def minimum_words_for_type(content_type: str) -> int:
    return MINIMUM_WORDS_BY_TYPE.get(content_type or "", 220)

def target_word_range_for_type(content_type: str) -> tuple[int, int]:
    return TARGET_WORD_RANGES_BY_TYPE.get(content_type or "", (500, 650))

def minimum_paragraphs_for_type(content_type: str) -> int:
    return MINIMUM_PARAGRAPHS_BY_TYPE.get(content_type or "", 3)


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
        if len(snippet)<35 and len(locator)<8:
            errors.append(f"fact_ledger[{i}] thiếu trích đoạn chứng cứ hoặc vị trí kiểm tra")
        if snippet and not evidence_matches_title(claim,snippet,minimum_overlap=0.10):
            errors.append(f"fact_ledger[{i}] trích đoạn chưa thể hiện từ khóa của dữ kiện")
        if str(fact.get('importance') or '').lower()=='core':
            families={domain_key(u) for u in refs if domain_key(u)}
            primary={str(u).strip() for u in (primary_urls or [])}
            if len(families)<2 and not any(str(u).strip() in primary for u in refs):
                errors.append(f"fact_ledger[{i}] là dữ kiện cốt lõi nhưng chưa được đối chiếu độc lập hoặc nguồn gốc")
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
            if not page or len(snippet_norm)<35 or snippet_norm not in page["text"]:
                continue
            snippet_numbers=set(re.findall(r"\d+(?:[.,]\d+)?", snippet))
            if claim_numbers and not claim_numbers.issubset(snippet_numbers):
                continue
            snippet_terms={x for x in re.findall(r"[\wÀ-ỹ]{4,}", snippet.casefold())}
            overlap=len(claim_terms & snippet_terms)/max(1,len(claim_terms))
            if overlap<0.20:
                continue
            sequence_ok, sequence_score = _claim_sentence_sequence_match(claim, snippet)
            if not sequence_ok:
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
                f"fact_ledger[{i}] không có trích đoạn nguyên văn vừa tồn tại trên trang nguồn vừa khớp thứ tự/quan hệ dữ kiện; "
                "có thể đã đảo chủ thể, đối tượng hoặc diễn giải quá xa nguồn"
            )
            enriched.append(fact)
            continue
        if importance=="core" and not verified_primary and len(verified_items)<2:
            errors.append(f"fact_ledger[{i}] là dữ kiện cốt lõi nhưng chưa có chứng cứ nguyên văn từ hai nguồn độc lập hoặc một nguồn chính")
            enriched.append(fact)
            continue

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
            sequence_ok, _ = _claim_sentence_sequence_match(
                str(fact.get("claim") or ""), str(item.get("snippet") or "")
            )
            if not sequence_ok:
                errors.append(
                    f"fact_ledger[{i}] claim không còn khớp thứ tự/quan hệ với trích đoạn nguồn "
                    "(có thể đã đảo chủ thể, đối tượng hoặc chiều dữ kiện)"
                )
                continue
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
        if str(fact.get("importance") or "supporting").casefold()=="core":
            if not verified_primary and len(verified_families)<2:
                errors.append(f"fact_ledger[{i}] thiếu chứng cứ cốt lõi độc lập ở bước xuất bản")
    return errors


def validate_body_fact_coverage(body, fact_ledger):
    """Fail closed when body paragraphs introduce numeric facts absent from the ledger."""
    paragraphs=body if isinstance(body,list) else re.split(r"\n\s*\n",str(body or ""))
    ledger_text=" ".join(
        str(item.get("claim") or "") for item in (fact_ledger or []) if isinstance(item,dict)
    )
    ledger_numbers=set(re.findall(r"\d+(?:[.,]\d+)?",ledger_text))
    errors=[]
    for idx, paragraph in enumerate(paragraphs,1):
        text=str(paragraph or "")
        # Ignore editorial paragraph labels such as "Đoạn 1"; they are structure,
        # not factual quantities or dates.
        numeric_text=re.sub(r"(?i)\bđoạn\s+\d+\b"," ",text)
        numbers=set(re.findall(r"\d+(?:[.,]\d+)?",numeric_text))
        missing=sorted(numbers-ledger_numbers)
        if missing:
            errors.append(
                f"Đoạn {idx} có số liệu/ngày tháng chưa xuất hiện trong fact ledger: {', '.join(missing[:6])}"
            )
    return errors

def validate_article_quality(article: dict, min_words=None, min_paragraphs=None):
    errors = []
    title = str(article.get("title") or "").strip()
    summary = str(article.get("summary") or "").strip()
    body = article.get("body") or []
    stats = body_stats(body)
    if article.get("fact_ledger"):
        errors.extend(validate_body_fact_coverage(body, article.get("fact_ledger") or []))
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
    editorial_parts=[x.strip() for x in re.split(r"[.;!?]",editorial_value) if len(x.strip())>=18]
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
}

def evidence_matches_title(title: str, evidence: str, minimum_overlap=0.20) -> bool:
    title_tokens={x for x in re.findall(r"[a-z0-9À-ỹ]+",str(title or "").casefold()) if len(x)>2 and x not in _TITLE_STOPWORDS}
    if len(title_tokens)<2:
        return False
    evidence_tokens=set(re.findall(r"[a-z0-9À-ỹ]+",str(evidence or "")[:5000].casefold()))
    overlap=len(title_tokens & evidence_tokens)/len(title_tokens)
    return overlap>=minimum_overlap
