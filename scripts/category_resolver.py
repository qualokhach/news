"""Deterministic routing of an article into one of the four public sections.

The AI model labels each draft, but it often files Vietnamese stories under "world" (the
catch-all). This module corrects that with explicit signals, never with a model call:

* Vietnamese place names, institutions and "Việt Nam" in the title / summary / body;
* where the sources come from (Vietnamese outlets .vn, or a Vietnamese feed hint);
* whether the headline is clearly about a foreign country.

Only the world <-> vietnam boundary is touched. A Vietnamese football or technology story
keeps its sports / technology section, because those sections are the closer fit.
"""
import re
from urllib.parse import urlparse

# 34 provinces/cities after the 2025 merger plus the 63 former provinces and the best-known
# cities. Words that are also ordinary Vietnamese/English words are matched only with their
# "tỉnh"/"thành phố" prefix or with a negative look-ahead (see AMBIGUOUS).
PLACES = (
    'hà nội','hồ chí minh','tp hcm','tp.hcm','sài gòn','thủ đức','đà nẵng','hải phòng','cần thơ','huế',
    'thừa thiên huế','quảng ninh','quảng nam','quảng ngãi','quảng bình','quảng trị','nghệ an','thanh hóa',
    'thanh hoá','hà tĩnh','nam định','ninh bình','hưng yên','hải dương','bắc ninh','bắc giang','bắc kạn',
    'thái nguyên','phú thọ','vĩnh phúc','tuyên quang','hà giang','lào cai','yên bái','sơn la','điện biên',
    'lai châu','lạng sơn','hà nam','lâm đồng','gia lai','kon tum','đắk lắk','đắk nông','khánh hòa','khánh hoà',
    'ninh thuận','bình thuận','bình phước','bình dương','bình định','phú yên','đồng nai','bà rịa','vũng tàu',
    'tây ninh','long an','tiền giang','bến tre','trà vinh','vĩnh long','đồng tháp','an giang','kiên giang',
    'hậu giang','sóc trăng','bạc liêu','cà mau','phú quốc','biên hòa','nha trang','đà lạt','hạ long','quy nhơn',
    'buôn ma thuột','pleiku','rạch giá','cam ranh','sa pa','hội an','phan thiết','long xuyên','mỹ tho','cần giờ',
    'côn đảo','mộc châu','phong nha','trường sa','hoàng sa','đồng bằng sông cửu long','tây nguyên',
)
# Ordinary words that equal a province name: accepted only as "tỉnh X" / "thành phố X" / "tp X".
AMBIGUOUS = ('hòa bình','hoà bình','cao bằng','vinh','thái bình','bình thuận')
INSTITUTIONS = (
    # Only markers that cannot plausibly refer to another country. Generic terms such as
    # "quốc hội", "nghị định", "bộ y tế" or "tổng bí thư" are deliberately excluded: they
    # appear in stories about the US, China, Ukraine, etc.
    'việt nam','vn-index','vn index','vnindex','đồng việt nam','việt nam đồng','người dân việt nam',
    'công an tp','công an tỉnh','công an phường','công an xã','công an quận','công an huyện','bộ công an',
    'ủy ban nhân dân','ubnd','hội đồng nhân dân','hđnd','chính phủ việt nam','ngân hàng nhà nước',
    'tổng bí thư tô lâm','thủ tướng phạm minh chính','viettel','vingroup','vinfast','petrolimex','vietcombank',
)
FOREIGN = (
    'mỹ','hoa kỳ','trung quốc','nga','ukraine','israel','iran','gaza','palestine','syria','iraq','yemen','houthi',
    'hàn quốc','triều tiên','nhật bản','ấn độ','pakistan','afghanistan','indonesia','philippines','thái lan',
    'malaysia','singapore','campuchia','lào','myanmar','úc','new zealand','canada','mexico','brazil','argentina',
    'venezuela','cuba','colombia','peru','chile','anh','pháp','đức','ý','tây ban nha','bồ đào nha','hà lan','bỉ',
    'thụy sĩ','thụy điển','na uy','đan mạch','phần lan','ba lan','hungary','romania','hy lạp','thổ nhĩ kỳ','ai cập',
    'nam phi','nigeria','kenya','ethiopia','sudan','congo','saudi arabia','ả rập','qatar','liên minh châu âu',
    'nato','liên hợp quốc','washington','moscow','kyiv','bắc kinh','tokyo','seoul','paris','london','berlin',
    'brussels','trump','biden','putin','zelensky','netanyahu',
)


def _norm(text):
    text=re.sub(r'[^\w\u00C0-\u1EF9]+',' ',str(text or '').casefold(),flags=re.UNICODE)
    return re.sub(r'\s+',' ',text).strip()


def _has(text, term):
    # 'thái bình' must not match 'Thái Bình Dương' (Pacific).
    pattern=r'(?<![\w\u00C0-\u1EF9])'+re.escape(term)+r'(?![\w\u00C0-\u1EF9])'
    if term=='thái bình':
        pattern+=r'(?!\s+dương)'
    if term=='bình dương':
        pattern=r'(?<!thái\s)'+pattern   # "Thái Bình Dương" is the Pacific Ocean
    return re.search(pattern,text) is not None


def vietnam_markers(text):
    """Distinct Vietnam-specific markers found in text."""
    t=_norm(text)
    found={p for p in PLACES if _has(t,_norm(p))}
    found|={i for i in INSTITUTIONS if _has(t,_norm(i))}
    for term in AMBIGUOUS:
        if re.search(r'(?<![\w\u00C0-\u1EF9])(?:tỉnh|thành phố|tp)\s+'+re.escape(term)+r'(?![\w\u00C0-\u1EF9])'
                     +(r'(?!\s+dương)' if term=='thái bình' else ''),t):
            found.add(term)
    return found


def foreign_markers(text):
    t=_norm(text)
    return {f for f in FOREIGN if _has(t,f)}


def _is_vn_domain(url):
    host=(urlparse(str(url or '')).hostname or '').lower()
    return host.endswith('.vn') or host.endswith('vnexpress.net')


def resolve_category(category, title, summary='', body=None, source_urls=(), hint=''):
    """Return the best section among world/vietnam for an article labelled world/vietnam.

    sports and technology labels are kept. Rules, strongest first:
      world -> vietnam  : Vietnam marker in title or summary;
                          or two distinct markers in the body;
                          or Vietnamese outlet/feed hint with no foreign-focused headline.
      vietnam -> world  : no Vietnam marker anywhere, no .vn source, no Vietnamese hint and
                          the headline names a foreign country.
    """
    if category not in ('world','vietnam'):
        return category
    body_text=' '.join(body) if isinstance(body,list) else str(body or '')
    head=f'{title or ""} {summary or ""}'
    head_vn=vietnam_markers(head)
    all_vn=vietnam_markers(f'{head} {body_text}')
    urls=[u for u in (source_urls or []) if u]
    vn_sources=sum(1 for u in urls if _is_vn_domain(u))
    vn_feed=(hint=='vietnam') or (urls and vn_sources==len(urls))
    foreign_title=foreign_markers(title)
    if category=='world':
        if head_vn or len(all_vn)>=2:
            return 'vietnam'
        if vn_feed and not foreign_title:
            return 'vietnam'
        return 'world'
    # category == 'vietnam'
    if not all_vn and not vn_sources and hint!='vietnam' and foreign_title:
        return 'world'
    return 'vietnam'
