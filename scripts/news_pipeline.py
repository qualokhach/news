#!/usr/bin/env python3
"""AppNho News research pipeline: discover, collect primary-source evidence, draft and queue candidates.

RSS headlines are discovery-only. The script prepares quality-gated candidates in
`data/research_queue.json`; publication is handled separately by `publish_ready.py`.
"""
import os, re, json, html, hashlib, urllib.request, urllib.error, difflib, time, csv
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET
from category_resolver import resolve_category
from content_quality import (complete_fact_ledger, compute_verified_numbers, ready_candidate_errors, classify_risk, validate_article_quality, validate_fact_ledger, verify_fact_ledger_against_pages, repair_fact_ledger_anchors, source_independence, domain_key, is_primary_source_type, validate_r3_content, evidence_matches_title, ttl_for_data_type, is_commercial_license, minimum_words_for_type, minimum_paragraphs_for_type, target_word_range_for_type)

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ROOT / 'config/feeds.json'
ARTICLES = ROOT / 'data/articles.json'
ARCHIVE = ROOT / 'data/archive_articles.json'
PENDING = ROOT / 'data/pending.json'
SEEN = ROOT / 'data/seen_items.json'
RESEARCH_QUEUE = ROOT / 'data/research_queue.json'
SOURCE_DIRECTORY = ROOT / 'config/source_directory.csv'
TIMEOUT = 8
UA = 'AppNhoNewsBot/1.0 (+https://github.com/qualokhach/news)'
MAX_NEW_PER_RUN = int(os.getenv('MAX_ARTICLES_PER_RUN', '8'))
MAX_CANDIDATE_GROUPS_PER_RUN = max(1, int(os.getenv('MAX_CANDIDATE_GROUPS_PER_RUN', '8')))
MAX_PENDING = 5000
MAX_RESEARCH_QUEUE = 150
# Optional model overrides are honored only when explicitly configured. By default, discover
# currently available models at runtime and prefer lightweight/high-quota free candidates.
GEMINI_MODEL = os.getenv('GEMINI_MODEL', '').strip()
GROK_MODEL = os.getenv('GROK_MODEL', '').strip()
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', '').strip()
MAX_GEMINI_CALLS_PER_RUN = max(0, int(os.getenv('MAX_GEMINI_CALLS_PER_RUN', '24')))
MAX_CLOUDFLARE_CALLS_PER_RUN = max(0, int(os.getenv('MAX_CLOUDFLARE_CALLS_PER_RUN', '10')))
MAX_OPENROUTER_CALLS_PER_RUN = max(0, int(os.getenv('MAX_OPENROUTER_CALLS_PER_RUN', '16')))
GEMINI_CALLS_THIS_RUN = 0
CLOUDFLARE_CALLS_THIS_RUN = 0
OPENROUTER_CALLS_THIS_RUN = 0
MODEL_DISCOVERY_CACHE = {}
THUMBS = {
    'world': 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_gioi.png',
    'vietnam': 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Viet_Nam.png',
    'sports': 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_thao.png',
    'technology': 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Cong_Nghe.png',
}
CATEGORY_LABELS = {'world':'Thế giới','vietnam':'Việt Nam','sports':'Thể thao','technology':'Công nghệ'}
# Bilingual stop words plus generic newsroom vocabulary. These words often
# create accidental matches across unrelated RSS headlines ("after", "test",
# "drop", "bid", "Olympic", etc.) and must not be treated as topic identity.
STOP = set('''và là của có cho trong với một những các được từ đến khi tại về theo sau trước đang đã sẽ này đó như nhưng vì để nếu thì hoặc cũng vào hơn rất nhiều người ngày năm tháng tin bài thông tin
a an the and or but if then than so as at by for from in into of on onto out over per to up via with without after before during amid around about against between beyond despite following near past since through toward under until upon versus while within
this that these those it its they them their he she his her we our you your who what when where why how which whose whom
new latest live update updates news report reports says said according amid after ahead back still just also one two three
team teams player players club clubs season match matches game games games win wins won loss losses defeat defeats race racewalk sports sport
world cup league championship championships olympic olympics bid race forced modernise modernize midterms
ra sao nay tây bảo hiểm bảo hiểm bảo hiem kết đầu mùa năm nay
test tests earnings revenue profit profits shares stock stocks market markets company companies business businesses
'''.split())


# Bootstrap boundary for this repository's first windowed run. Vietnam time 2026-10-24 06:00.
# Once feed_cursors exists, each source advances independently only after its feed parses.
INITIAL_WINDOW_START = os.getenv('NEWS_INITIAL_WINDOW_START', '2026-10-24T06:00:00+07:00')

def now_iso(): return datetime.now(timezone.utc).isoformat()
def as_utc(value):
    if not value: return None
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception: return None
def is_in_window(published_at, window_start, window_end):
    published=as_utc(published_at); start=as_utc(window_start); end=as_utc(window_end)
    return bool(published and start and end and start < published <= end)
def clean(s):
    s = html.unescape(s or '')
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()
def get_text(node, names):
    """Read RSS/Atom fields by local XML name, including namespaced Dublin Core tags."""
    wanted={str(name).split('}')[-1].split(':')[-1].casefold() for name in names}
    for child in node.iter():
        local=str(child.tag).split('}')[-1].split(':')[-1].casefold()
        if local not in wanted:
            continue
        if child.text and child.text.strip():
            return child.text.strip()
        # Atom links store their target in href rather than text.
        href=child.attrib.get('href') or child.attrib.get('{http://www.w3.org/1999/xlink}href')
        if href:
            return href.strip()
    return ''

def parse_date(raw):
    """Parse RFC822, ISO-8601, common publisher date strings and Unix timestamps."""
    if raw is None:
        return ''
    value=str(raw).strip()
    if not value:
        return ''
    candidates=[value]
    # RSS feeds sometimes wrap the date in a JSON-LD/HTML attribute.
    if value.isdigit() and len(value) in (10,13):
        try:
            stamp=float(value) / (1000 if len(value)==13 else 1)
            return datetime.fromtimestamp(stamp,timezone.utc).isoformat()
        except (ValueError,OverflowError,OSError):
            pass
    try:
        d=parsedate_to_datetime(value)
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    normalized=value.replace('Z','+00:00')
    try:
        d=datetime.fromisoformat(normalized)
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    for fmt in (
        '%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M','%Y/%m/%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S','%d/%m/%Y %H:%M','%Y-%m-%d',
        '%d-%m-%Y %H:%M:%S','%d-%m-%Y %H:%M'
    ):
        try:
            d=datetime.strptime(value,fmt).replace(tzinfo=timezone.utc)
            return d.isoformat()
        except ValueError:
            continue
    return ''

def publication_date_from_html(raw_html):
    """Extract only publication timestamps from HTML metadata; never use crawl time."""
    text=raw_html.decode('utf-8','replace') if isinstance(raw_html,bytes) else str(raw_html or '')
    patterns=(
        r'<meta[^>]+(?:property|name)=["\\\'](?:article:published_time|datePublished|date|pubdate|publishdate)["\\\'][^>]+content=["\\\']([^"\\\']+)',
        r'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+(?:property|name)=["\\\'](?:article:published_time|datePublished|date|pubdate|publishdate)["\\\']',
        r'"datePublished"\\s*:\\s*"([^"]+)"',
        r'"dateCreated"\\s*:\\s*"([^"]+)"'
    )
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if match:
            parsed=parse_date(html.unescape(match.group(1)))
            if parsed:
                return parsed
    return ''

def fetch(url, accept='text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', limit=1_500_000):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if r.status != 200: raise RuntimeError(f'HTTP {r.status}')
        return r.read(limit)

def robots_allowed(url):
    """Respect robots.txt; this is a crawl rule check, not a copyright license."""
    parts=urlsplit(url)
    if parts.scheme not in ('http','https') or not parts.netloc:
        return False
    robots_url=f'{parts.scheme}://{parts.netloc}/robots.txt'
    parser=RobotFileParser()
    parser.set_url(robots_url)
    try:
        req=urllib.request.Request(robots_url,headers={'User-Agent':UA})
        with urllib.request.urlopen(req,timeout=5) as response:
            raw=response.read(256_000).decode('utf-8','replace')
        parser.parse(raw.splitlines())
        return parser.can_fetch(UA,url)
    except urllib.error.HTTPError as e:
        if e.code==404:
            parser.parse([])
            return True
        return False
    except Exception:
        return False

def canon(url):
    url = (url or '').strip()
    url = re.sub(r'#.*$', '', url)
    # Strip common tracking parameters without changing article identity parameters.
    url = re.sub(r'([?&])(utm_[^=&]+|fbclid|gclid)=[^&]*', '', url, flags=re.I)
    url = url.rstrip('?&')
    return url.rstrip('/')

def load_source_directory():
    # Source metadata for attribution and source-role hints; not a license allowlist.
    rows=[]
    if not SOURCE_DIRECTORY.exists():
        return rows
    try:
        with SOURCE_DIRECTORY.open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f,delimiter=';'))
    except Exception as e:
        print(f'[WARN] Source directory unavailable: {e}')
    for row in rows:
        row['_domain']=domain_key(row.get('URL chính thức',''))
        row['_primary_candidate']=is_primary_source_type(row.get('Loại nguồn',''))
        row['_source_family']=row.get('source_family') or row.get('Tên đầu mối','') or row['_domain']
    return rows

SOURCE_ROWS = load_source_directory()

def source_info(url):
    domain=domain_key(url)
    # BBC publishes through both bbc.com and bbc.co.uk; treat them as one publisher family.
    domain_aliases={'bbc.co.uk':'bbc.com'}
    domain=domain_aliases.get(domain,domain)
    matches=[r for r in SOURCE_ROWS if r.get('_domain') and (domain==r['_domain'] or domain.endswith('.'+r['_domain']))]
    if not matches:
        return {'name':domain or 'Nguồn công khai','source_type':'Chưa phân loại','is_primary':False,
                'is_primary_for_claim':False,'source_family':domain,'directory_access_status':'not_listed',
                'access_status':'UNVERIFIED','terms_status':'UNVERIFIED','commercial_use_status':'UNVERIFIED','terms_url':'','robots_url':'','allowed_fields':'','license_notes':'Not verified'}
    row=max(matches,key=lambda r:len(r.get('_domain','')))
    return {
        'name':(row.get('Tên đầu mối') or domain),
        'source_type':row.get('Loại nguồn') or 'Chưa phân loại',
        'is_primary':bool(row.get('_primary_candidate')),
        'is_primary_for_claim':False,
        'source_family':row.get('_source_family') or domain,
        'directory_access_status':(row.get('Trạng thái kiểm tra') or 'Chưa kiểm tra'),
        'access_status':(row.get('access_status') or 'UNVERIFIED').upper(),
        'terms_status':(row.get('terms_status') or 'UNVERIFIED').upper(),
        'commercial_use_status':(row.get('commercial_use_status') or 'UNVERIFIED').upper(),
        'terms_url':row.get('terms_url',''),
        'robots_url':row.get('robots_url',''),
        'allowed_fields':row.get('allowed_fields',''),
        'license_notes':row.get('license_notes',''),
    }

def mark_group_retry(group, reason, now=None):
    now=now or datetime.now(timezone.utc)
    for item in group:
        item['attempts']=int(item.get('attempts',0))+1
        item['last_error']=clean(reason)[:300]
        if item['attempts']>=3:
            item['status']='HOLD'
            item['retry_after']=(now+timedelta(hours=72)).isoformat()
            item['attempts']=0
        else:
            item['status']='retry'
            item['retry_after']=(now+timedelta(hours=6)).isoformat()

def parse_feed(payload, feed):
    root = ET.fromstring(payload)
    atom = '{http://www.w3.org/2005/Atom}'
    nodes = root.findall('.//item') or root.findall(f'.//{atom}entry')
    out=[]
    for node in nodes:
        title=clean(get_text(node,['title',f'{atom}title']))
        link=get_text(node,['link'])
        if not link:
            ln=node.find(f'{atom}link')
            if ln is not None: link=ln.attrib.get('href','')
        date=get_text(node,['pubDate','published','updated','date','created','datePublished','dateCreated','issued'])
        # Do not retain publisher summaries/full-text excerpts: RSS is used for metadata-only discovery.
        description=''
        link=canon(link)
        if not title or not link.startswith(('https://','http://')): continue
        uid=hashlib.sha256(link.encode()).hexdigest()[:20]
        out.append({'id':uid,'discovery_title':title[:240],'source_url':link,'source_name':feed['name'],
                    'category':feed['category'],'source_published_at':parse_date(date),'discovered_at':now_iso(),
                    'source_terms_url':feed.get('terms_url',''),'source_feed_domain':domain_key(feed.get('url','')),
                    'discovery_summary':'','discovery_mode':'metadata_only','status':'queued','attempts':0})
    return out

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip=0; self.parts=[]; self.title=False; self.in_title=False
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','nav','footer','header','aside','noscript','svg','form'): self.skip+=1
        if tag=='title': self.in_title=True
        if tag in ('p','h1','h2','h3','article','main','li','br'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style','nav','footer','header','aside','noscript','svg','form') and self.skip: self.skip-=1
        if tag=='title': self.in_title=False
        if tag in ('p','h1','h2','h3','article','main','li'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip:
            t=re.sub(r'\s+',' ',data).strip()
            if t: self.parts.append(t)
def research_access_mode(url, feed_domain=None):
    """Choose approved research or limited factual-reference mode without implying a license."""
    info=source_info(url)
    access=str(info.get('access_status','UNVERIFIED')).upper()
    terms=str(info.get('terms_status','UNVERIFIED')).upper()
    if access=='BLOCKED' or terms=='BLOCKED':
        raise PermissionError('Source explicitly marked BLOCKED')
    if info.get('directory_access_status')=='not_listed':
        host=domain_key(url)
        feed_host=str(feed_domain or '').strip().casefold()
        if not feed_host or not (host==feed_host or host.endswith('.'+feed_host)):
            raise PermissionError(f'Unlisted article host {host} does not match configured feed publisher {feed_host or "(missing)"}')
    if access=='RESEARCH_ALLOWED' and terms=='VERIFIED':
        mode='APPROVED_RESEARCH'
    elif os.getenv('NEWS_PUBLIC_FACTUAL_RESEARCH','').strip().lower() in {'1','true','yes'}:
        parts=urlsplit(url)
        if parts.scheme!='https' or not parts.netloc:
            raise PermissionError('Limited factual research requires HTTPS')
        mode='LIMITED_FACTUAL_REFERENCE'
    else:
        raise PermissionError('Source is not approved for research in this run')
    if not robots_allowed(url):
        raise PermissionError('robots.txt disallows access or could not be verified')
    return mode

def extract_page(url, access_mode=None):
    mode=access_mode or research_access_mode(url)
    raw=fetch(url, limit=1_500_000)
    text=raw.decode('utf-8','replace')
    p=TextExtractor()
    try: p.feed(text)
    except Exception: pass
    lines=[re.sub(r'\s+',' ',x).strip() for x in ''.join(p.parts).splitlines()]
    lines=[x for x in lines if len(x)>35]
    page_text=' '.join(lines).casefold()
    blocked_markers=('verify you are human','complete the captcha','captcha challenge','access denied',
                     '403 forbidden','subscribe to continue reading','this article is for subscribers',
                     'đăng nhập để tiếp tục đọc','đăng ký để đọc tiếp','nội dung dành cho thuê bao')
    if any(marker in page_text for marker in blocked_markers):
        raise PermissionError('Source page appears to require subscription, CAPTCHA or restricted access')
    # Remove cookie, subscription, and common UI noise; keep only a bounded factual excerpt.
    cleaned=[]; seen=set()
    for line in lines:
        low=line.lower()
        if any(x in low for x in ['accept all cookies','subscribe to our newsletter','sign up to our','advertisement','đăng ký nhận tin','đọc thêm','xem thêm']): continue
        if line not in seen: cleaned.append(line); seen.add(line)
    return '\n'.join(cleaned)[:6500]

def tokens(s):
    return {x.lower() for x in re.findall(r'[\wÀ-ỹ]{3,}', s or '', flags=re.UNICODE) if x.lower() not in STOP}
def similarity(a,b):
    ta,tb=tokens(a),tokens(b)
    jac=len(ta&tb)/max(1,len(ta|tb))
    seq=difflib.SequenceMatcher(None,(a or '').lower(),(b or '').lower()).ratio()
    return max(jac,seq*0.72)
def headlines_related(a,b,min_similarity=0.08,min_shared_tokens=2):
    """Require shared topic-bearing terms; sequence similarity is unsafe for headlines."""
    ta,tb=tokens(a),tokens(b)
    shared=ta & tb
    if len(shared)<min_shared_tokens:
        return False
    # Use token overlap only here; retain the broader similarity metric for
    # duplicate-title detection elsewhere in the pipeline.
    return len(shared)/max(1,len(ta|tb))>=min_similarity

def build_research_dossier(group, evidence):
    """Build a factual inventory before AI writing; source length is not a quality proxy."""
    pages=[]
    fact_rows=[]
    for source in group:
        url=source.get('source_url','')
        page=str(evidence.get(url,'') or '')
        if not page.strip():
            continue
        info=source_info(url)
        family=(info.get('source_family') or domain_key(url) or url).casefold()
        pages.append({'url':url,'family':family,'is_primary':bool(info.get('is_primary')),
                      'source_type':info.get('source_type','')})
        # Short official notices and concise specialist reports can carry high-value facts.
        # Count factual propositions, not characters or repeated sentence length.
        for sentence in re.split(r'(?<=[.!?。！？])\s+|\n+',page):
            sentence=clean(sentence)
            if len(sentence.split()) < 5:
                continue
            low=sentence.casefold()
            if any(x in low for x in ('cookie policy','subscribe to our newsletter','all rights reserved',
                                      'đăng ký nhận tin','đọc thêm','privacy policy')):
                continue
            has_number=bool(re.search(r'\d',sentence))
            has_date=bool(re.search(r'\b(?:20\d{2}|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b',low))
            # Page extraction is often normalized to lowercase. Retain factual sentences
            # with quantities/dates, plus sufficiently specific propositions for later claim checks.
            if has_number or has_date or len(sentence.split()) >= 9:
                fact_rows.append({'url':url,'family':family,'text':sentence[:900],
                                  'numeric':has_number,'date':has_date})
    # Deduplicate within a publisher family, but do not require other publishers to use
    # identical wording: paraphrased independent reporting is normal.
    unique={}
    for row in fact_rows:
        key=re.sub(r'\W+',' ',row['text'].casefold()).strip()
        if not key:
            continue
        bucket=unique.setdefault(key,{**row,'families':set(),'urls':set()})
        bucket['families'].add(row['family']); bucket['urls'].add(row['url'])
    facts=list(unique.values())
    families={x['family'] for x in pages if x['family']}
    primary_pages=[x for x in pages if x['is_primary']]
    # Genre follows the number and diversity of usable factual units, not page length.
    # Analysis is reserved for genuinely broad dossiers; otherwise use a concise report.
    cross_family_facts=sum(1 for x in facts if len(x['families']) >= 2)
    if len(families)>=4 and len(facts)>=12 and cross_family_facts>=2:
        content_type='news_analysis'
    elif len(families)>=3 and len(facts)>=7:
        content_type='short_explainer'
    else:
        content_type='quick_update'
    low,high=target_word_range_for_type(content_type)
    return {
        'source_count':len(pages),'independent_families':len(families),
        'evidence_characters':sum(len(str(evidence.get(x['url'],'') or '')) for x in pages),
        'distinct_fact_units':len(facts),'corroborated_fact_units':cross_family_facts,
        'numeric_fact_units':sum(1 for x in facts if x['numeric']),
        'primary_source_count':len(primary_pages),'content_type':content_type,
        'target_words':(low+high)//2,
        'fact_units':[{'text':x['text'],'source_families':sorted(x['families']),
                       'source_urls':sorted(x['urls']),'numeric':x['numeric'],'date':x['date']}
                      for x in facts[:40]],
        'source_inventory':pages
    }


def research_dossier_ready(dossier):
    """Evidence readiness gate. No minimum character/page-length threshold is used."""
    if not dossier:
        return False, 'Không có hồ sơ dữ liệu nghiên cứu.'
    families=int(dossier.get('independent_families',0) or 0)
    source_count=int(dossier.get('source_count',0) or 0)
    inventory=dossier.get('source_inventory') or []
    has_primary=any(isinstance(x,dict) and x.get('is_primary') for x in inventory)
    if source_count<1 or (families<2 and not has_primary):
        return False, 'Chưa có hai nhóm nguồn độc lập hoặc một nguồn gốc/chính thức phù hợp.'
    if int(dossier.get('distinct_fact_units',0) or 0)<3:
        return False, 'Hồ sơ chưa có tối thiểu ba dữ kiện cụ thể có thể khai thác.'
    if not dossier.get('fact_units'):
        return False, 'Không trích xuất được đơn vị dữ kiện từ nội dung nguồn.'
    # One suitable primary source can establish facts within its authority; it does not
    # automatically validate claims outside its remit. Claim-level proof remains mandatory.
    return True, 'Hồ sơ có dữ kiện cụ thể; từng claim vẫn phải qua xác minh trước xuất bản.'


def source_score(item, group_count, usage_penalty=0):
    score=35
    dt=item.get('source_published_at')
    if dt:
        try:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(dt.replace('Z','+00:00'))).total_seconds()/3600
            score += 20 if age<=24 else 14 if age<=48 else 7 if age<=72 else -20
        except Exception: score-=3
    else: score-=5
    score += min(20,(group_count-1)*10)
    cat=item.get('category')
    if cat in CATEGORY_LABELS: score+=10
    if len(tokens(item.get('discovery_title','')))>=5: score+=5
    if any(x in (item.get('discovery_title','').lower()) for x in ['breaking','cập nhật','kết quả','official','chính thức','ra mắt','ban hành','giành','vô địch']): score+=5
    # A source used in recent successful publications receives a penalty,
    # preserving freshness while encouraging editorial variety across runs.
    score -= min(24, max(0, int(usage_penalty)))
    return min(100,score)
def slugify(s):
    import unicodedata
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    return re.sub(r'-+','-',re.sub(r'[^a-z0-9]+','-',s)).strip('-')[:90] or hashlib.sha1(s.encode()).hexdigest()[:12]
def word_count(text): return len(re.findall(r'\S+', text or ''))

def _sanitize_ai_json_text(txt):
    """Repair only JSON string-encoding defects; never invent or alter field values."""
    txt=(txt or '').strip()
    txt=re.sub(r'^```(?:json)?\s*|\s*```$', '', txt, flags=re.I)
    if not txt.startswith('{'):
        a=txt.find('{'); b=txt.rfind('}')
        if a >= 0 and b > a: txt=txt[a:b+1]
    out=[]; in_string=False; escaped=False; i=0
    valid_escapes='"\\/bfnrt'
    while i < len(txt):
        ch=txt[i]
        if not in_string:
            if ch=='"': in_string=True
            out.append(ch); i+=1; continue
        if escaped:
            if ch=='u':
                code=txt[i+1:i+5]
                if len(code)==4 and all(c in '0123456789abcdefABCDEF' for c in code):
                    out.append('\\u'+code); i+=5; escaped=False; continue
                # Preserve a literal backslash-u sequence instead of treating it as JSON Unicode.
                out.append('\\\\u'); i+=1; escaped=False; continue
            if ch in valid_escapes:
                out.append('\\'+ch); i+=1; escaped=False; continue
            # Invalid escape such as \q: encode the slash as a literal character.
            out.append('\\\\'+ch); i+=1; escaped=False; continue
        if ch=='\\':
            escaped=True; i+=1; continue
        if ch=='"':
            in_string=False; out.append(ch); i+=1; continue
        if ord(ch)<0x20:
            out.append('\\n' if ch in '\r\n' else ('\\t' if ch=='\t' else ' ')); i+=1; continue
        out.append(ch); i+=1
    if escaped:
        out.append('\\\\')
    return ''.join(out)

def _recover_truncated_json(txt):
    """Rebuild valid JSON from a reply cut off mid-way (token limit) or with a broken tail.

    Walks the text, remembers every position just before a top-level-ish comma together with
    the brackets still open there, and tries to close the document at the latest position that
    parses. Only the incomplete tail is dropped; no value is invented.
    """
    txt=(txt or '').strip()
    a=txt.find('{')
    if a<0: return None
    txt=txt[a:]
    stack=[]; in_string=False; escaped=False; cuts=[]
    for i,ch in enumerate(txt):
        if in_string:
            if escaped: escaped=False
            elif ch=='\\': escaped=True
            elif ch=='"': in_string=False
            continue
        if ch=='"': in_string=True
        elif ch in '{[': stack.append('}' if ch=='{' else ']')
        elif ch in '}]':
            if stack: stack.pop()
        elif ch==',':
            cuts.append((i,''.join(reversed(stack))))
    candidates=[]
    # Whole text, closing a dangling string and any open brackets.
    if not in_string:
        # Cut cleanly after a finished value. When the reply stops inside a string, that last
        # value is incomplete and is dropped rather than kept truncated.
        candidates.append(txt+''.join(reversed(stack)))
    for i,closers in reversed(cuts[-80:]):
        candidates.append(txt[:i]+closers)
    for cand in candidates:
        try:
            obj=json.loads(_sanitize_ai_json_text(cand))
            if isinstance(obj,dict) and obj.get('body'):
                return obj
        except Exception:
            continue
    return None


def parse_ai_json(txt):
    # Workers AI can return a structured object directly instead of a JSON string.
    # Accept that documented response shape, but validate it with the same schema.
    if isinstance(txt, dict):
        obj=txt
    elif isinstance(txt, str):
        cleaned=_sanitize_ai_json_text(txt)
        try:
            obj=json.loads(cleaned)
        except json.JSONDecodeError as exc:
            obj=_recover_truncated_json(txt)
            if obj is None:
                raise ValueError(f'AI returned malformed JSON ({exc.msg} at character {exc.pos})') from exc
            print('[JSON] Recovered a truncated/malformed AI reply by closing its incomplete tail.')
    else:
        raise ValueError(f'AI response must be JSON text or object, got {type(txt).__name__}')
    if not isinstance(obj, dict):
        raise ValueError('AI response is not a JSON object')
    # Only the article itself is mandatory. Metadata the pipeline can derive, and the fact ledger
    # (rebuilt from the Research dossier), get safe defaults instead of failing the draft.
    obj.setdefault('seo_title',obj.get('title',''))
    obj.setdefault('meta_description',obj.get('summary',''))
    obj.setdefault('keywords',[]); obj.setdefault('source_index',0)
    obj.setdefault('risk_level','R1'); obj.setdefault('freshness_ttl_hours',24)
    obj.setdefault('fact_ledger',[]); obj.setdefault('editorial_value','')
    required={'publish','title','summary','category','body'}
    missing=required-set(obj)
    if missing:
        raise ValueError('AI response missing fields: '+', '.join(sorted(missing)))
    if not isinstance(obj.get('body'), list) or not isinstance(obj.get('keywords'), list):
        raise ValueError('AI response body/keywords have wrong types')
    if any(not isinstance(x,str) for x in obj['body']):
        raise ValueError('AI response body must contain strings only')
    if any(not isinstance(x,str) for x in obj['keywords']):
        raise ValueError('AI response keywords must contain strings only')
    if not isinstance(obj.get('fact_ledger'), list) or any(not isinstance(x,dict) for x in obj['fact_ledger']):
        raise ValueError('AI response fact_ledger must contain objects only')
    if not isinstance(obj.get('publish'), bool):
        raise ValueError('AI response publish must be boolean')
    return obj

def _post_json(url, payload, headers, provider):
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers=headers,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=90) as r: data=json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail=e.read().decode('utf-8','replace')[:350]
        # Never include request URLs, because Gemini's key is carried in its query string.
        raise RuntimeError(f'{provider} HTTP {e.code}: {detail}')
    return data

def get_json(url, headers=None, provider='API'):
    req=urllib.request.Request(url,headers={'User-Agent':UA,**(headers or {})})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            return json.loads(r.read(2_000_000).decode('utf-8','replace'))
    except urllib.error.HTTPError as e:
        detail=e.read().decode('utf-8','replace')[:220]
        raise RuntimeError(f'{provider} model discovery HTTP {e.code}: {detail}')

def discover_gemini_models():
    key=os.getenv('GEMINI_API_KEY','').strip()
    if not key: return []
    data=get_json('https://generativelanguage.googleapis.com/v1beta/models?'+urlencode({'key':key,'pageSize':1000}),provider='Gemini')
    # Google's live model list does not expose per-account free-tier eligibility. Keep a
    # conservative allowlist of models currently documented with free-tier pricing, then
    # intersect it with models actually returned for this key. Update this list after reviewing pricing docs.
    free_names={'gemini-3.5-flash-lite','gemini-3.1-flash-lite'}
    candidates=[]
    for m in data.get('models',[]):
        name=m.get('name','').removeprefix('models/')
        methods=m.get('supportedGenerationMethods',[])
        if not name or 'generateContent' not in methods or name not in free_names: continue
        if GEMINI_MODEL and name != GEMINI_MODEL: continue
        low=name.lower()
        if any(x in low for x in ('embedding','aqa','image','audio','tts','robotics','computer-use')): continue
        # Prefer lightweight Flash-Lite models; avoid preview/experimental models for reliability.
        score=0
        if 'flash-lite' in low: score+=100
        elif 'flash' in low: score+=70
        elif 'pro' in low: score+=10
        if any(x in low for x in ('preview','experimental','exp-')): score-=60
        candidates.append((score,name))
    return [x[1] for x in sorted(candidates,reverse=True)]

def discover_xai_models():
    """Discover a current, text-capable Grok model from the authenticated xAI catalog.

    No retired model slug is hard-coded. We prefer grok-4.7 when the account exposes
    it; otherwise choose the lowest-priced current Grok text model returned by xAI.
    """
    key=os.getenv('XAI_API_KEY','').strip()
    if not key:
        return []
    headers={'Authorization':'Bearer '+key}
    rows=[]
    # The language-model endpoint includes model capabilities and pricing. Fall back
    # to /models for accounts or API versions where that endpoint is unavailable.
    try:
        data=get_json('https://api.x.ai/v1/language-models',headers,'Grok/xAI')
        rows=data.get('models',[]) if isinstance(data,dict) else []
        if not rows:
            raise RuntimeError('xAI language-model catalog returned no models')
    except Exception:
        data=get_json('https://api.x.ai/v1/models',headers,'Grok/xAI')
        rows=data.get('data',[]) if isinstance(data,dict) else []
    candidates=[]
    grok_rows=0; missing_price=0; over_budget=0
    max_input=float(os.getenv('XAI_MAX_INPUT_USD_PER_MILLION','5'))
    max_output=float(os.getenv('XAI_MAX_OUTPUT_USD_PER_MILLION','20'))
    override_available=any(
        isinstance(item,dict) and str(item.get('id') or item.get('name','').removeprefix('models/')).strip()==GROK_MODEL
        for item in rows
    ) if GROK_MODEL else False
    for item in rows:
        if not isinstance(item,dict):
            continue
        mid=str(item.get('id') or item.get('name','').removeprefix('models/')).strip()
        low=mid.casefold()
        if not low.startswith('grok-') or any(x in low for x in ('imagine','image','video','audio','voice','embedding')):
            continue
        grok_rows+=1
        if override_available and mid != GROK_MODEL:
            continue
        # xAI prices are cents per 100M tokens in the language-model catalog.
        pin=item.get('prompt_text_token_price')
        pout=item.get('completion_text_token_price')
        if pin is None or pout is None:
            # An explicitly configured model is an intentional operator choice.
            # Permit it when the catalog omits pricing, but never guess a price.
            if not (GROK_MODEL and mid == GROK_MODEL):
                missing_price+=1
                continue
            input_usd = output_usd = None
        else:
            try:
                input_usd=float(pin)/10_000
                output_usd=float(pout)/10_000
            except (TypeError,ValueError):
                if not (GROK_MODEL and mid == GROK_MODEL):
                    missing_price+=1
                    continue
                input_usd = output_usd = None
            if input_usd is not None and (input_usd < 0 or output_usd < 0 or input_usd > max_input or output_usd > max_output):
                over_budget+=1
                continue
        # Prefer the named flagship when present, otherwise lowest total price.
        preferred=0 if mid==GROK_MODEL and GROK_MODEL else (1 if mid=='grok-4.7' else 2)
        total_price=(input_usd+output_usd) if input_usd is not None else float('inf')
        candidates.append((preferred,total_price,mid))
    candidates.sort()
    if not candidates:
        if not grok_rows:
            print('[MODEL] Grok/xAI catalog returned no text Grok models.')
        elif missing_price and not GROK_MODEL:
            print(f'[MODEL] Grok/xAI found {grok_rows} text model(s), but {missing_price} lacked usable pricing; set repository variable GROK_MODEL to an explicitly approved model slug.')
        elif over_budget:
            print(f'[MODEL] Grok/xAI found {grok_rows} text model(s), but {over_budget} exceeded configured price ceilings (${max_input}/M input, ${max_output}/M output).')
    return [x[2] for x in candidates[:3]]

OPENROUTER_BLOCKED_MODEL_HINTS=('inkling','thinkingmachines','coder','code-','-code')
OPENROUTER_PREFERRED_FAMILIES=('llama-3.3','llama-3.1','gpt-oss','gemma','qwen','mistral','deepseek')

def discover_openrouter_models():
    key=os.getenv('OPENROUTER_API_KEY','').strip()
    if not key: return []
    data=get_json('https://openrouter.ai/api/v1/models?output_modalities=text',{'Authorization':'Bearer '+key},'OpenRouter')
    candidates=[]
    for m in data.get('data',[]):
        mid=m.get('id','')
        pricing=m.get('pricing') or {}
        try: prompt_price=float(pricing.get('prompt','-1'))
        except (TypeError,ValueError): prompt_price=-1
        try: completion_price=float(pricing.get('completion','-1'))
        except (TypeError,ValueError): completion_price=-1
        # Hard guard: only use explicitly free models. Never silently fall back to paid models.
        if not mid.endswith(':free') or prompt_price != 0 or completion_price != 0: continue
        if OPENROUTER_MODEL and mid != OPENROUTER_MODEL: continue
        try: context=int(m.get('context_length') or 0)
        except (TypeError,ValueError): context=0
        if context and context < 12000: continue
        low=mid.lower()
        # Models that answer HTTP 403 for plain API calls ("only available on agentic harnesses").
        if any(x in low for x in OPENROUTER_BLOCKED_MODEL_HINTS): continue
        # Favor general text/instruct models and moderate model sizes; avoid vision-only models.
        score=0
        if any(x in low for x in OPENROUTER_PREFERRED_FAMILIES): score+=60
        if any(x in low for x in ('flash','mini','small','lite','8b','14b','free')): score+=20
        if any(x in low for x in ('vl','vision','audio','embedding','guard')): score-=30
        if context>=32000: score+=5
        candidates.append((score,mid))
    return [x[1] for x in sorted(candidates,reverse=True)]

def gemini(prompt, model):
    key=os.getenv('GEMINI_API_KEY','').strip()
    if not key: raise RuntimeError('Gemini key missing')
    endpoint=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}'
    payload={'systemInstruction':{'parts':[{'text':(
        'Bạn là nhà báo/phóng viên chuyên nghiệp của một tòa soạn báo điện tử tiếng Việt. Hãy viết bài báo hoàn chỉnh theo đề tài, thể loại và độ dài được giao. Viết độc lập, chính xác, dễ đọc, không phóng đại. '
        'Chỉ dùng dữ kiện có trong bằng chứng được cung cấp. Không bịa số liệu, phát biểu, nguyên nhân, '
        'dự báo hoặc trích dẫn. Không sao chép câu chữ nguồn. Nếu bằng chứng không đủ để viết bài đạt độ dài yêu cầu mà không suy diễn, trả về JSON với publish=false. '
        'Không nhồi từ khóa, không lặp ý để kéo dài. Output chỉ JSON hợp lệ, không markdown.')}]},
        'contents':[{'role':'user','parts':[{'text':prompt}]}],
        'generationConfig':{'temperature':0.25,'responseMimeType':'application/json','maxOutputTokens':7000}}
    data=_post_json(endpoint,payload,{'Content-Type':'application/json'},'Gemini/'+model)
    parts=data.get('candidates',[{}])[0].get('content',{}).get('parts',[])
    txt=''.join(p.get('text','') for p in parts).strip()
    if not txt: raise RuntimeError('Gemini returned empty content or blocked output')
    return parse_ai_json(txt)

CLOUDFLARE_MODEL = '@cf/meta/llama-3.3-70b-instruct-fp8-fast'

def _extract_cloudflare_text(value):
    """Extract generated text from Workers AI response variants safely."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts=[_extract_cloudflare_text(item) for item in value]
        return ''.join(part for part in parts if part).strip()
    if isinstance(value, dict):
        # A structured JSON object may itself be the model output. Check it
        # before wrapper keys so fields such as "content" cannot mask it.
        if {'publish','title','summary','body'}.issubset(value):
            return json.dumps(value,ensure_ascii=False)
        # Workers AI may wrap text or a structured object in nested fields.
        for key in ('response','output_text','text','content','message'):
            if key in value:
                extracted=_extract_cloudflare_text(value.get(key))
                if extracted:
                    return extracted
        choices=value.get('choices')
        if isinstance(choices,list) and choices:
            extracted=_extract_cloudflare_text(choices[0])
            if extracted:
                return extracted
    return ''

def cloudflare_workers_ai(prompt):
    """Generate a structured draft with the fixed, preflight-tested Workers AI model."""
    account_id=os.getenv('CLOUDFLARE_ACCOUNT_ID','').strip()
    token=os.getenv('CLOUDFLARE_API_TOKEN','').strip()
    if not account_id or not token:
        raise RuntimeError('Cloudflare Workers AI Account ID or API Token missing')
    endpoint=('https://api.cloudflare.com/client/v4/accounts/'+account_id+
              '/ai/run/'+CLOUDFLARE_MODEL)
    system=('Bạn là nhà báo/phóng viên chuyên nghiệp của một tòa soạn báo điện tử tiếng Việt. Hãy viết bài báo hoàn chỉnh theo đề tài và độ dài được giao; '
            'chỉ dùng dữ kiện trong nguồn, không bịa số liệu, phát biểu hay trích dẫn; không sao chép câu chữ nguồn. '
            'Nếu bằng chứng không đủ, trả publish=false. Chỉ trả về một đối tượng JSON hợp lệ, không markdown.')
    payload={
        'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
        'temperature':0.25,
        'max_tokens':7000
    }
    data=_post_json(endpoint,payload,
                    {'Authorization':'Bearer '+token,'Content-Type':'application/json'},
                    'Cloudflare Workers AI/'+CLOUDFLARE_MODEL)
    if isinstance(data,dict) and data.get('success') is False:
        errors=data.get('errors') or []
        detail='; '.join(str(x.get('message','')) for x in errors if isinstance(x,dict))
        raise RuntimeError('Cloudflare Workers AI API reported failure'+(': '+detail[:240] if detail else ''))
    result=data.get('result') if isinstance(data,dict) else None
    content=_extract_cloudflare_text(result)
    if not content:
        raise RuntimeError('Cloudflare Workers AI returned empty or unsupported response content')
    return parse_ai_json(content)

def xai_responses(prompt, model):
    """Call xAI's primary Responses API; avoid the legacy Chat Completions endpoint."""
    key=os.getenv('XAI_API_KEY','').strip()
    if not key:
        raise RuntimeError('Grok/xAI key missing')
    system=('Bạn là nhà báo/phóng viên chuyên nghiệp của một tòa soạn báo điện tử tiếng Việt. Hãy viết bài báo hoàn chỉnh theo đề tài và độ dài được giao; '
            'chỉ dùng dữ kiện trong nguồn, không bịa số liệu, phát biểu hay trích dẫn; không sao chép câu chữ nguồn. '
            'Nếu bằng chứng không đủ, trả publish=false. Chỉ trả về một đối tượng JSON hợp lệ, không markdown.')
    payload={
        'model':model,
        'input':[
            {'role':'system','content':system},
            {'role':'user','content':prompt}
        ],
        'temperature':0.25,
        'max_output_tokens':7000,
        'store':False
    }
    data=_post_json('https://api.x.ai/v1/responses',payload,
                    {'Authorization':'Bearer '+key,'Content-Type':'application/json'},
                    'Grok/xAI Responses/'+model)
    parts=[]
    for item in data.get('output',[]) if isinstance(data,dict) else []:
        if not isinstance(item,dict) or item.get('type')!='message':
            continue
        for content in item.get('content',[]) or []:
            if isinstance(content,dict) and content.get('type')=='output_text':
                parts.append(content.get('text',''))
    txt=''.join(parts).strip()
    if not txt:
        raise RuntimeError('Grok/xAI Responses returned empty output')
    return parse_ai_json(txt)

def openai_compatible(prompt, provider, key_env, endpoint, model, extra_headers=None, json_mode=True):
    key=os.getenv(key_env,'').strip()
    if not key: raise RuntimeError(f'{provider} key missing')
    headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'}
    headers.update(extra_headers or {})
    payload={'model':model,'messages':[
        {'role':'system','content':('Bạn là nhà báo/phóng viên chuyên nghiệp của một tòa soạn báo điện tử tiếng Việt. Hãy viết bài báo hoàn chỉnh theo đề tài và độ dài được giao; '
         'chỉ dùng dữ kiện trong nguồn, không bịa số liệu, phát biểu hay trích dẫn; không sao chép câu chữ nguồn. '
         'Nếu bằng chứng không đủ, trả publish=false. Chỉ trả về một đối tượng JSON hợp lệ, không markdown.')},
        {'role':'user','content':prompt}], 'temperature':0.25,'max_tokens':7000}
    if json_mode: payload['response_format']={'type':'json_object'}
    data=_post_json(endpoint,payload,headers,provider+'/'+model)
    choices=data.get('choices') or []
    content=(choices[0].get('message') or {}).get('content') if choices else ''
    if isinstance(content,list): content=''.join(x.get('text','') for x in content if isinstance(x,dict))
    if not content: raise RuntimeError(f'{provider} returned empty content')
    return parse_ai_json(content)

class EditorialEvidenceGateError(RuntimeError):
    """Deterministic evidence failure: do not spend more provider calls on the same facts."""


def generate_with_fallback(prompt, validator=None):
    """Try providers in order; run the full local article gate before accepting a draft.
    validator(candidate, provider_label) must raise when the draft is not publishable.
    """
    providers=[]
    definitions=[
        ('Gemini','GEMINI_API_KEY',discover_gemini_models,lambda model,p:gemini(p,model)),
        ('Cloudflare Workers AI','CLOUDFLARE_API_TOKEN',
         lambda: [CLOUDFLARE_MODEL],
         lambda model,p:cloudflare_workers_ai(p)),
        ('OpenRouter','OPENROUTER_API_KEY',discover_openrouter_models,
         lambda model,p:openai_compatible(p,'OpenRouter','OPENROUTER_API_KEY',
             'https://openrouter.ai/api/v1/chat/completions',model,
             {'HTTP-Referer':'https://appnho.io.vn/','X-Title':'AppNho News'},json_mode=False))
    ]
    for name,env,discover,call in definitions:
        if not os.getenv(env,'').strip():
            print(f'[SKIP] {name}: key not configured')
            continue
        try:
            if name not in MODEL_DISCOVERY_CACHE:
                MODEL_DISCOVERY_CACHE[name]=discover()
            models=MODEL_DISCOVERY_CACHE[name]
            if not models:
                print(f'[WARN] {name}: no currently eligible models discovered')
                continue
            providers.append((name,models[:(5 if name=='OpenRouter' else 3)],call))
            print(f'[MODEL] {name}: {len(models)} eligible model(s); selected {models[0]}')
        except Exception as e:
            MODEL_DISCOVERY_CACHE[name]=[]
            print(f'[WARN] {name} model discovery failed: {str(e)[:180]}')
    errors=[]
    assigned_match=re.search(r'Thể loại bắt buộc: (quick_update|short_explainer|news_analysis|long_analysis)',prompt)
    assigned_type=assigned_match.group(1) if assigned_match else ''
    global GEMINI_CALLS_THIS_RUN, CLOUDFLARE_CALLS_THIS_RUN, OPENROUTER_CALLS_THIS_RUN
    for name,models,call in providers:
        for model in models:
            cap={'Gemini':MAX_GEMINI_CALLS_PER_RUN,
                 'Cloudflare Workers AI':MAX_CLOUDFLARE_CALLS_PER_RUN,
                 'OpenRouter':MAX_OPENROUTER_CALLS_PER_RUN}[name]
            used={'Gemini':GEMINI_CALLS_THIS_RUN,
                  'Cloudflare Workers AI':CLOUDFLARE_CALLS_THIS_RUN,
                  'OpenRouter':OPENROUTER_CALLS_THIS_RUN}[name]
            if used>=cap:
                print(f'[SKIP] {name}: per-run call cap reached ({cap}); trying next provider.')
                break
            last_validation_error=''
            transient_retry=False
            for attempt in range(2):
                try:
                    if name=='Gemini': GEMINI_CALLS_THIS_RUN+=1
                    elif name=='Cloudflare Workers AI': CLOUDFLARE_CALLS_THIS_RUN+=1
                    else: OPENROUTER_CALLS_THIS_RUN+=1
                    retry_prompt=prompt
                    if attempt and not transient_retry:
                        retry_prompt += (
                            "\n\nYÊU CẦU BIÊN TẬP LẠI TOÀN BỘ BẢN THẢO: "
                            "Bạn vẫn đang đảm nhiệm vai trò nhà báo/phóng viên chuyên nghiệp. "
                            "Bản trước chưa đạt kiểm định vì lỗi sau: " + last_validation_error[:1200] + ". "
                            "Hãy viết lại toàn bộ bài, giữ đúng content_type đã chọn và đạt ít nhất số từ tối thiểu "
                            "được quy định cho thể loại đó. Thể loại được giao là " + (assigned_type or "đã xác định") + ". "
                            "Không được đổi sang thể loại ngắn hơn chỉ để vượt kiểm định. "
                            "Bản thảo phải đạt khoảng " + str(target_word_range_for_type(assigned_type)[0] if assigned_type else 250) + "-" + str(target_word_range_for_type(assigned_type)[1] if assigned_type else 350) + " từ trong body. "
                            "Hãy viết đầy đủ hơn (mục tiêu "+str(target_word_range_for_type(assigned_type)[0] if assigned_type else 250)+"+ từ). "
                            "Bổ sung bối cảnh, diễn biến và phân tích cụ thể chỉ từ bằng chứng đã cung cấp; "
                            "không lặp ý, không bịa dữ kiện. Trả lại toàn bộ JSON hợp lệ theo đúng schema."
                        )
                    result=call(model,retry_prompt)
                    if not result.get('publish'):
                        reason=clean(result.get('reason') or 'model declined to draft')
                        raise ValueError('Model returned publish=false for a Research-approved dossier: '+reason[:240])
                    if result.get('publish'):
                        body=[clean(x) for x in result.get('body',[]) if clean(x)]
                        words=word_count(' '.join(body))
                        ctype=str(result.get('content_type') or 'short_explainer')
                        if assigned_type and ctype != assigned_type:
                            raise ValueError(f'AI changed assigned content_type ({assigned_type} -> {ctype})')
                        minimum=minimum_words_for_type(assigned_type or ctype)
                        min_paragraphs=minimum_paragraphs_for_type(assigned_type or ctype)
                        if len(body)<min_paragraphs or words<minimum:
                            raise ValueError(
                                f'Generated draft below safety floor ({words}/{minimum} words, '
                                f'{len(body)}/{min_paragraphs} paragraphs, type={ctype}); '
                                'minimum editorial word count was not met'
                            )
                        if result.get('category') not in CATEGORY_LABELS:
                            raise ValueError('Generated draft has invalid category')
                    provider_label=name+':'+model
                    result['_provider']=provider_label
                    if validator and result.get('publish'):
                        # Do not accept a draft merely because its JSON and length
                        # look valid. Run fact-ledger, source-independence, risk,
                        # similarity and article-quality gates before provider fallback ends.
                        validator(result,provider_label)
                    print(f'[AI] Response received from {name} model={model}'+(' after repair retry' if attempt else ''))
                    return result,provider_label
                except Exception as e:
                    message=str(e)
                    # Research has already sealed a dossier before Writing starts.
                    # A provider's failed interpretation/ledger formatting is a writing
                    # failure, not permission to reopen Research or discard the candidate.
                    # Continue through configured providers and retain the sealed dossier.
                    last_validation_error=message
                    secret_env={'Gemini':'GEMINI_API_KEY','Cloudflare Workers AI':'CLOUDFLARE_API_TOKEN',
                                'OpenRouter':'OPENROUTER_API_KEY'}[name]
                    secret=os.getenv(secret_env,'')
                    if secret: message=message.replace(secret,'[redacted]')
                    account=os.getenv('CLOUDFLARE_ACCOUNT_ID','') if name=='Cloudflare Workers AI' else ''
                    if account: message=message.replace(account,'[account-redacted]')
                    message=message[:180]
                    errors.append(f'{name}/{model}: {message}')
                    retryable=('malformed JSON' in message or 'Generated draft below safety floor' in message or
                               'AI response missing fields' in message or 'AI response body/keywords' in message or
                               'publish=false' in message or 'fact_ledger[' in message or
                               'Quality gate failed:' in message or 'R2 requires' in message or
                               'R3 requires' in message or 'source_type' in message)
                    current={'Gemini':GEMINI_CALLS_THIS_RUN,
                             'Cloudflare Workers AI':CLOUDFLARE_CALLS_THIS_RUN,
                             'OpenRouter':OPENROUTER_CALLS_THIS_RUN}[name]
                    overloaded=('HTTP 503' in message or 'HTTP 500' in message or 'HTTP 502' in message or 'HTTP 504' in message
                                or ('HTTP 429' in message and name=='Gemini'))
                    if attempt==0 and overloaded and name!='OpenRouter' and current<cap:
                        print(f'[RETRY] {name}/{model}: temporary overload; waiting 8s before one retry.')
                        transient_retry=True
                        time.sleep(8)
                        continue
                    if attempt==0 and retryable and current<cap:
                        print(f'[RETRY] {name}/{model}: asking the same model to correct JSON/length once.')
                        continue
                    print(f'[WARN] {name} model unavailable/invalid; trying next provider ({message})')
                    break
                time.sleep(0.4)
    if not errors:
        exhausted=[]
        if os.getenv('GEMINI_API_KEY','').strip() and GEMINI_CALLS_THIS_RUN>=MAX_GEMINI_CALLS_PER_RUN: exhausted.append('Gemini')
        if os.getenv('CLOUDFLARE_API_TOKEN','').strip() and CLOUDFLARE_CALLS_THIS_RUN>=MAX_CLOUDFLARE_CALLS_PER_RUN: exhausted.append('Cloudflare Workers AI')
        if os.getenv('OPENROUTER_API_KEY','').strip() and OPENROUTER_CALLS_THIS_RUN>=MAX_OPENROUTER_CALLS_PER_RUN: exhausted.append('OpenRouter')
        if exhausted: raise RuntimeError('Per-run provider call budgets exhausted: '+', '.join(exhausted))
        raise RuntimeError('No configured provider/model is currently eligible; check API keys and model discovery logs.')
    raise RuntimeError('All discovered eligible AI models failed: '+' | '.join(errors[-12:]))


def make_prompt(group, evidence, discovery_leads=None, research_dossier=None):
    sources=[]
    for x in group:
        info=source_info(x['source_url'])
        sources.append({
            'name':x['source_name'],'url':x['source_url'],
            'published_at':x.get('source_published_at',''),
            'headline':x['discovery_title'],
            'source_type':info.get('source_type','Chưa phân loại'),
            'source_family':info.get('source_family') or domain_key(x.get('source_url','')),
            'source_role':'primary_candidate' if info['is_primary'] else 'independent_publisher_reference',
            'user_supplied_context_for_research_only':x.get('manual_context','')[:2500],
            'page_evidence':evidence.get(x['source_url'],'')[:5200]
        })
    assigned_topic = (group[0].get('discovery_title') if group else '') or 'Chủ đề được thể hiện trong hồ sơ nguồn'
    # Genre and word range are fixed by the API-free research dossier.
    dossier=research_dossier or build_research_dossier(group,evidence)
    assigned_type=dossier.get('content_type','quick_update')
    target_low,target_high=target_word_range_for_type(assigned_type)
    assigned_target=(target_low+target_high)//2
    instructions = r'''VAI TRÒ NGHỀ NGHIỆP
Bạn là nhà báo/phóng viên chuyên nghiệp (professional journalist and reporter), được giao viết bài cho một tòa soạn báo điện tử. Hãy làm việc như người trực tiếp chịu trách nhiệm về chất lượng bài báo trước khi xuất bản: đọc kỹ hồ sơ nguồn, xác định thông tin đã được xác minh, chọn góc tiếp cận phù hợp và viết thành tác phẩm báo chí hoàn chỉnh. Không viết theo kiểu chatbot trả lời câu hỏi, không viết ghi chú nghiên cứu, không viết bản tóm tắt sơ sài.

ĐỀ TÀI VÀ NHIỆM VỤ
Viết một bài báo hoàn chỉnh cho AppNho News về sự kiện/chủ đề thể hiện trong tiêu đề phát hiện và các tài liệu nguồn bên dưới. Tự xác định góc báo chí cụ thể, phù hợp với dữ kiện. Tiêu đề phát hiện chỉ là đầu mối đề tài, không mặc nhiên là sự thật đã được xác minh.

THỂ LOẠI VÀ ĐỘ DÀI ĐÃ ĐƯỢC TÒA SOẠN GIAO
Thể loại bắt buộc: {assigned_type}
Độ dài mục tiêu cụ thể: {assigned_target} từ trong phần body.
Khoảng biên tập chấp nhận: {target_low}-{target_high} từ. Hãy nhắm tới khoảng này. Bài ngắn hơn một chút vẫn được chấp nhận nếu đủ thông tin; tuyệt đối không độn chữ hay lặp ý để đủ số từ.
Không tự chọn thể loại khác, không tự rút ngắn bài và không trả bản tóm tắt thay cho bài báo. Đây là chỉ tiêu giao việc trực tiếp của biên tập viên. Hãy viết đủ độ dài bằng cách khai thác các dữ kiện, bối cảnh và diễn biến đã có trong hồ sơ. Nếu hồ sơ không đủ căn cứ để hoàn thành, trả publish=false và giải thích chính xác dữ liệu còn thiếu.

Độ dài tính trên phần body, không tính tiêu đề, sapo, keywords, fact_ledger hoặc metadata. Trước khi trả kết quả, tự kiểm tra độ dài body. Không tự ý chọn thể loại ngắn chỉ để né yêu cầu độ dài. Chọn thể loại tương ứng với góc tiếp cận và mức độ bằng chứng; nếu hồ sơ không đủ dữ liệu để viết một bài hoàn chỉnh đạt mức tối thiểu mà không suy diễn, hãy trả publish=false và nêu rõ phần dữ liệu còn thiếu. Không được xuất bản một bản thảo ngắn hơn mức tối thiểu rồi coi đó là bài hoàn chỉnh.

YÊU CẦU TÁC NGHIỆP VÀ BIÊN TẬP
1. Chỉ chuyển hóa hồ sơ nghiên cứu đã hoàn tất thành bài báo. KHÔNG thực hiện nghiên cứu mới, KHÔNG tự bổ sung dữ kiện từ kiến thức nền hoặc trí nhớ. Đọc toàn bộ bằng chứng trang nguồn được cung cấp trước khi viết. Phân biệt dữ kiện đã xác minh, thông tin do một bên tuyên bố và phần chưa thể kiểm chứng.
2. Xây dựng bài có tiêu đề, sapo và phần thân bài hoàn chỉnh. Body phải gồm nhiều đoạn văn có nội dung, triển khai theo trình tự hợp lý; dùng tiêu đề phụ trong body khi cần thiết.
3. Mở bài nêu sự kiện/vấn đề chính, thông tin mới và ý nghĩa trực tiếp đối với độc giả.
4. Phát triển bài bằng những chi tiết có thật trong hồ sơ: diễn biến, bối cảnh, mốc thời gian, số liệu, các bên liên quan, phản ứng, tác động hoặc điểm còn chưa rõ — chỉ đưa vào khi nguồn thực sự chứng minh.
5. Bài phải có giá trị biên tập độc lập: chọn góc nhìn riêng, đặt các dữ kiện cạnh nhau để làm rõ điều mà một bản tin tóm tắt chưa giải thích; phân tích hệ quả hoặc giới hạn của thông tin khi có căn cứ. Không được bịa trải nghiệm tác nghiệp, phỏng vấn, khảo sát hay quan sát hiện trường.
6. Không sao chép, dịch sát, viết lại từng đoạn hoặc ghép cơ học nội dung từ RSS/bài báo nguồn. Diễn đạt bằng cấu trúc và câu chữ riêng; chỉ trích dẫn nguyên văn trong fact_ledger để chứng minh dữ kiện, không đưa trích dẫn giả vào bài.
7. Không lặp ý để tăng số từ. Mỗi đoạn phải bổ sung dữ kiện, bối cảnh hoặc phân tích cụ thể. Không dùng lời khuyên chung chung, câu kết sáo rỗng hoặc nhận định không gắn với sự kiện.
8. Không tự tạo số liệu, ngày tháng, phát ngôn, nguyên nhân, động cơ, dự báo, tên người/tổ chức hoặc quan hệ nhân quả. Không biến suy đoán thành sự thật.
9. Nếu nguồn có quan điểm khác nhau, trình bày đúng chủ thể và mức độ chắc chắn; không tự cân bằng giả tạo giữa nguồn có chứng cứ mạnh và yếu.
10. Kết bài phải khép lại vấn đề bằng thông tin, hệ quả hoặc câu hỏi còn bỏ ngỏ có căn cứ; không dùng lời kêu gọi độc giả theo dõi.

QUY TẮC NGUỒN VÀ KIỂM CHỨNG
- RSS/headline chỉ dùng để phát hiện đề tài. Không dùng mô tả RSS làm bằng chứng cho dữ kiện trọng yếu.
- Chỉ publish=true khi có đủ căn cứ. Không tự tạo URL, số liệu, phát biểu, nguyên nhân, dự báo, nhân vật hoặc trích dẫn.
- Ưu tiên tài liệu gốc và nguồn chính thức. Nhiều trang đăng lại cùng một thông cáo không phải nguồn độc lập.
- Nếu chỉ có một nguồn thứ cấp, không đủ căn cứ cho bài phân tích; trả publish=false và nêu rõ lý do.
- Mỗi bài cần ít nhất 3 dữ kiện có thể kiểm tra trong fact_ledger. Hồ sơ Research đã qua cổng sẵn sàng và là căn cứ tác nghiệp đã đóng; không tự chạy lại đánh giá đủ/thiếu nguồn bằng một thuật toán khác, không trả publish=false chỉ vì từng claim không được lặp nguyên văn ở hai trang. Hãy viết từ fact_units và page_evidence đã cung cấp. Mỗi claim phải bằng tiếng Việt và chỉ nêu điều nguồn thực sự hỗ trợ. KHÔNG cần trích dẫn nguyên văn: hệ thống tự gắn bằng chứng từ hồ sơ Research. Mỗi mục fact_ledger chỉ cần claim (diễn đạt lại bằng tiếng Việt, bằng lời của bạn), source_urls (URL trong danh sách nguồn) và importance. Nếu hồ sơ có số liệu thì claim phải dùng đúng số liệu đó. Các nguồn độc lập có thể diễn đạt cùng dữ kiện bằng câu chữ khác nhau; không bắt buộc mọi nguồn phải lặp lại cùng một câu. Mức độc lập được đánh giá ở cấp hồ sơ bài viết: hồ sơ đã có ít nhất hai source family độc lập hoặc nguồn chính thức phù hợp; không yêu cầu mọi chi tiết hỗ trợ phải được hai nguồn nhắc lại. Với dữ kiện nhạy cảm/rủi ro cao hoặc tranh chấp, phải trình bày rõ mức độ xác nhận và chỉ khẳng định mạnh khi có nguồn gốc hoặc đối chiếu phù hợp. Không thêm URL ngoài danh sách.
- editorial_value BẮT BUỘC gồm 2-3 câu riêng biệt, mỗi câu kết thúc bằng dấu chấm và dài ít nhất 18 ký tự (không viết thành một câu duy nhất, không dùng khẩu hiệu). Nêu rõ đóng góp biên tập riêng bằng ít nhất hai ý cụ thể: câu hỏi được giải quyết, bối cảnh/so sánh/tác động/giới hạn nào được làm rõ.
- R2 cần kiểm tra số liệu, phương pháp, kỳ dữ liệu, bối cảnh và ít nhất một nguồn chính thức/nguồn gốc khi có thể.
- R3 không viết lời khuyên cá nhân về sức khỏe, đầu tư, pháp luật hoặc an toàn. Nếu không thể giới hạn nội dung ở mức tường thuật/thông tin chung dựa trên nguồn chính thức, trả publish=false.
- published_at là thời điểm sự kiện/nguồn công bố, không phải thời điểm AppNho xuất bản.
- source_index là chỉ số nguồn chính trong danh sách (0-based).
- Chỉ dùng tiếng Việt tự nhiên, không tự nhận AppNho đã phỏng vấn/tác nghiệp/khảo sát.
- Không chèn ghi chú nội bộ, lời kể quy trình nghiên cứu, hoặc câu “bài được AI tạo”.

ĐỊNH DẠNG ĐẦU RA
Chỉ trả về một JSON object hợp lệ, không markdown, không lời dẫn, có đúng các trường:
{"publish":true/false,"reason":"...","title":"...","summary":"...","category":"world|vietnam|sports|technology","content_type":"quick_update|short_explainer|news_analysis|long_analysis","seo_title":"...","meta_description":"...","keywords":["..."],"body":["đoạn 1","đoạn 2"],"source_index":0,"editorial_value":"đóng góp riêng cụ thể","risk_level":"R1|R2|R3","freshness_ttl_hours":24,"fact_ledger":[{"claim":"dữ kiện diễn đạt lại bằng tiếng Việt","source_urls":["URL có trong danh sách nguồn"],"importance":"core|supporting"}]}

Trước khi trả JSON, hãy tự rà soát: bài đã đạt mức tối thiểu của content_type chưa; từng đoạn có thông tin riêng chưa; dữ kiện có được fact_ledger chứng minh không; bài có góc biên tập riêng và không sao chép nguồn không. Nếu không đạt, sửa toàn bộ bản thảo hoặc trả publish=false. Không được bỏ qua yêu cầu độ dài.

Nguồn và bằng chứng đã thu thập:
'''
    leads=[{'headline':x.get('discovery_title',''),'publisher':x.get('source_name',''),
            'published_at':x.get('source_published_at',''),'summary_for_discovery_only':x.get('discovery_summary','')[:500]}
           for x in (discovery_leads or [])]
    instructions=instructions.replace('{assigned_type}',assigned_type).replace('{assigned_target}',str(assigned_target)).replace('{target_low}',str(target_low)).replace('{target_high}',str(target_high))
    assignment = ("VAI TRÒ: Nhà báo/phóng viên chuyên nghiệp.\n"
                  "ĐỀ TÀI CỤ THỂ ĐƯỢC GIAO: " + str(assigned_topic).strip() + "\n\n")
    return instructions + assignment + json.dumps({
        'research_readiness_dossier':dossier,
        'source_evidence_for_fact_check':sources,
        'discovery_leads_not_for_fact_claims':leads
    },ensure_ascii=False)


def normalize_vietnam_category(title, summary='', body=None, category='', source_urls=(), hint=''):
    """Route world/vietnam drafts to the closest section (see category_resolver.py)."""
    return resolve_category(category,title,summary,body,source_urls=source_urls,hint=hint)

def make_article(obj, group, evidence_pages=None):
    if not obj.get('publish'): return None
    title=clean(obj.get('title',''))
    summary=clean(obj.get('summary',''))
    category=obj.get('category','')
    body=[clean(p) for p in obj.get('body',[]) if clean(p)]
    content_type=str(obj.get('content_type') or '')
    if content_type not in {'quick_update','short_explainer','news_analysis','long_analysis'}:
        raise ValueError('AI output missing or invalid content_type; article type must be explicit')
    group_urls=[x.get('source_url') for x in group if x.get('source_url')]
    hints=[x.get('category') for x in group if x.get('category')]
    hint=max(set(hints),key=hints.count) if hints else ''
    category=normalize_vietnam_category(title, summary, body, category, group_urls, hint)
    required_paragraphs=minimum_paragraphs_for_type(content_type)
    if category not in CATEGORY_LABELS or not title or len(body)<required_paragraphs:
        raise ValueError(f'Article missing title/category/body structure; {content_type} requires at least {required_paragraphs} paragraphs')
    allowed_urls=[x.get('source_url') for x in group if x.get('source_url')]
    evidence_pages=evidence_pages or {}
    body_text=' '.join(body)
    for source_url,page_text in evidence_pages.items():
        if page_text and similarity(body_text,page_text)>0.52:
            raise ValueError('Bản thảo có mức tương đồng quá cao với nội dung nguồn; cần viết lại theo góc biên tập riêng')
    source_refs=[]

    for x in group:
        info=source_info(x.get('source_url',''))
        source_refs.append({
            'name':x.get('source_name') or info['name'],
            'url':x.get('source_url',''),
            'domain':domain_key(x.get('source_url','')),
            'source_type':info.get('source_type','Chưa phân loại'),
            'source_family':info.get('source_family') or domain_key(x.get('source_url','')),
            'source_role':'official_candidate' if info['is_primary'] else 'secondary',
            'is_primary':bool(info['is_primary']),
            'is_primary_for_claim':False,
            'directory_access_status':info['directory_access_status'],
            'terms_status':info['terms_status'],
            'commercial_use_status':info.get('commercial_use_status','UNVERIFIED'),
            'access_status':info.get('access_status','UNVERIFIED'),
            'research_mode':x.get('research_mode','LIMITED_FACTUAL_REFERENCE'),
            'reuse_mode':'FACTUAL_CITATION_ONLY',
            'source_published_at':x.get('source_published_at','')
        })
    primary_urls=[x.get('url') for x in source_refs if x.get('is_primary')]
    source_families={x.get('url'):x.get('source_family') or domain_key(x.get('url','')) for x in source_refs}
    # Repair only a mislabeled source_claim by anchoring it to an exact excerpt
    # already present in the Research-fetched page. No facts or source text are invented.
    # Research already sealed the facts. The model's ledger only says which facts it used, in its
    # own words; the evidence excerpts come from the verified Research fact units.
    dossier=build_research_dossier(group,evidence_pages)
    repaired_ledger=complete_fact_ledger(obj.get('fact_ledger'),dossier.get('fact_units',[]),
                                         evidence_pages,allowed_urls,primary_urls=primary_urls,minimum=3)
    ledger_errors, verified_ledger = verify_fact_ledger_against_pages(
        repaired_ledger, allowed_urls, evidence_pages,
        min_claims=3, primary_urls=primary_urls, source_families=source_families
    )
    if ledger_errors:
        raise ValueError('; '.join(ledger_errors))
    obj['fact_ledger'] = verified_ledger
    core_urls={
        str(item.get('source_url'))
        for fact in verified_ledger
        if isinstance(fact,dict) and str(fact.get('importance','')).lower()=='core'
        for item in (fact.get('evidence_by_source') or [])
        if isinstance(item,dict) and item.get('source_url')
    }
    for ref in source_refs:
        ref['is_primary_for_claim']=bool(ref.get('is_primary') and ref.get('url') in core_urls)
    source_count,has_primary,domains=source_independence(source_refs)
    risk=classify_risk(title,body,category)
    # Do not let the model inflate the risk tier with a generic label. The local
    # classifier applies the same policy used by publication validation.
    if source_count < 2 and not has_primary:
        raise ValueError('Need at least two independent source domains or one primary source')
    if risk=='R2' and not has_primary and source_count < 2:
        raise ValueError('R2 requires a primary source or at least two independent source families')
    if risk=='R3' and not has_primary:
        raise ValueError('R3 requires a primary/official source')
    if risk=='R3':
        advice=validate_r3_content(title,body)
        if advice:
            raise ValueError('R3 contains actionable personal advice: '+', '.join(advice[:4]))
    data_type=str(obj.get('data_type') or 'general')
    ttl_cap=ttl_for_data_type(data_type,risk)
    try: ttl=max(1,min(ttl_cap,int(obj.get('freshness_ttl_hours',ttl_cap))))
    except Exception: ttl=ttl_cap
    idx=obj.get('source_index',0)
    try: main=group[int(idx)]
    except Exception: main=group[0]
    pub=obj.get('published_at') or main.get('source_published_at') or now_iso()
    try:
        d=datetime.fromisoformat(pub.replace('Z','+00:00'))
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        pub=d.astimezone(timezone.utc).isoformat()
    except Exception:
        pub=main.get('source_published_at') or now_iso()
    ident=slugify(title)
    ident=ident[:72]+'-'+hashlib.sha1((main['source_url']+title).encode()).hexdigest()[:8]
    keywords=[clean(x)[:60] for x in obj.get('keywords',[]) if clean(x)][:8]
    if len(keywords)<4:
        keywords=list(dict.fromkeys(keywords+[title.split(':')[0],CATEGORY_LABELS[category],'tin tức '+CATEGORY_LABELS[category].lower()]))[:5]
    article={
        'id':ident,'title':title,'summary':summary[:360],'category':category,
        'source_name':main['source_name'],'source_url':main['source_url'],
        'published_at':pub,'fetched_at':now_iso(),'appnho_published_at':'',
        'content_type':content_type,'data_type':data_type,'collection':'current',
        'body':body,'generation_provider':obj.get('_provider',''),
        'seo_title':clean(obj.get('seo_title') or title)[:70],
        'meta_description':clean(obj.get('meta_description') or summary)[:160],
        'keywords':keywords,'slug':ident,'images':[],
        'content_image_url':'','content_image_alt':'','content_image_credit':'','content_image_credit_url':'',
        'word_count':word_count(' '.join(body)),'display_source':True,
        'source_urls':list(dict.fromkeys(x['source_url'] for x in group if x.get('source_url'))),
        'source_links':list(dict.fromkeys(x['source_url'] for x in group if x.get('source_url') and x['source_url']!=main['source_url'])),
        'source_references':source_refs,'fact_ledger':obj['fact_ledger'],
        'editorial_value':clean(obj.get('editorial_value')),
        'risk_level':risk,'verification_timestamp':now_iso(),'freshness_ttl_hours':ttl,
        'quality_version':'1.5','quality_status':'PASS'
    }
    errors,stats=validate_article_quality(article, evidence_pages=evidence_pages)
    if errors: raise ValueError('Quality gate failed: '+'; '.join(errors))
    # Later audits/publication no longer hold the source pages; record which body numbers
    # were verified against them now so every stage applies the same numeric rule.
    article['verified_numbers']=compute_verified_numbers(body,article['fact_ledger'],evidence_pages)
    article['quality_audit']={'checked_at':now_iso(),'status':'PASS','stats':stats,'independent_domains':domains,'primary_source_present':has_primary}
    return article

def find_licensed_image(article):
    """Find a relevant Wikimedia Commons image with machine-readable license metadata.
    Returns an image record only when title relevance and reusable license metadata are present.
    """
    query = article.get('title', '')[:180]
    params = {
        'action':'query','format':'json','generator':'search','gsrsearch':query,
        'gsrnamespace':'6','gsrlimit':'8','prop':'imageinfo','iiprop':'url|extmetadata',
        'iiurlwidth':'1200','origin':'*'
    }
    from urllib.parse import urlencode
    url='https://commons.wikimedia.org/w/api.php?'+urlencode(params)
    try:
        raw=fetch(url,accept='application/json',limit=1_500_000)
        data=json.loads(raw.decode('utf-8','replace'))
    except Exception as e:
        print(f'[INFO] Image search unavailable: {e}')
        return None
    pages=(data.get('query',{}).get('pages',{}) or {}).values()
    art_tokens=tokens(article.get('title',''))
    best=None; best_score=0
    for page in pages:
        infos=page.get('imageinfo') or []
        if not infos: continue
        info=infos[0]; meta=info.get('extmetadata',{})
        license_name=clean(meta.get('LicenseShortName',{}).get('value',''))
        license_url=clean(meta.get('LicenseUrl',{}).get('value',''))
        # Only select images whose licensing information is explicit.
        if not license_name or not license_url: continue
        if not is_commercial_license(license_name): continue
        image_title=clean(page.get('title','').replace('File:',''))
        image_tokens=tokens(image_title)
        score=len(art_tokens & image_tokens)/max(1,len(art_tokens))
        # A tiny relevance threshold avoids inserting generic unrelated images.
        if score < 0.12: continue
        if score > best_score:
            artist=clean(meta.get('Artist',{}).get('value','')) or 'Wikimedia Commons contributor'
            best={'url':info.get('thumburl') or info.get('url',''), 'alt':article.get('title',''),
                  'credit':artist, 'credit_url':info.get('descriptionurl') or 'https://commons.wikimedia.org/',
                  'license':license_name, 'license_url':license_url, 'score':score}
            best_score=score
    if best: print(f"[IMAGE] Relevant licensed image selected (relevance={best_score:.2f}, license={best['license']})")
    else: print('[IMAGE] No sufficiently relevant openly licensed image found; leaving article image empty.')
    return best

def metadata_only(article):
    return article


def search_official_sources(title, category, excluded_domains=None, limit=6, research_request=''):
    """Use Google News RSS for discovery only; resolve candidate links only to primary-source domains in the source inventory."""
    approved_primary_domains={r.get('_domain') for r in SOURCE_ROWS
                              if r.get('_primary_candidate')
                              and r.get('access_status','UNVERIFIED').upper()!='BLOCKED'
                              and r.get('terms_status','UNVERIFIED').upper()!='BLOCKED'}
    if not approved_primary_domains:
        print('[INFO] Official-source search skipped: no primary-source domains are present in the source inventory.')
        return []
    excluded_domains=set(excluded_domains or [])
    query='"'+clean(title)[:140]+'"'
    if research_request:
        query += ' ' + clean(research_request)[:100]
    params={'q':query,'hl':'vi','gl':'VN','ceid':'VN:vi'}
    search_url='https://news.google.com/rss/search?'+urlencode(params)
    try:
        if not robots_allowed(search_url):
            raise PermissionError('Google News RSS robots policy disallows discovery')
        payload=fetch(search_url,accept='application/rss+xml, application/xml, text/xml,*/*;q=0.5',limit=1_000_000)
        root=ET.fromstring(payload)
    except Exception as e:
        print(f'[INFO] Official-source discovery search unavailable: {type(e).__name__}: {e}')
        return []
    candidates=[]
    for node in root.findall('.//item')[:20]:
        link=get_text(node,['link'])
        headline=clean(get_text(node,['title']))
        pub=parse_date(get_text(node,['pubDate']))
        if not link or not headline:
            continue
        try:
            req=urllib.request.Request(link,headers={'User-Agent':UA,'Accept':'text/html,*/*;q=0.5'})
            with urllib.request.urlopen(req,timeout=12) as response:
                final_url=response.geturl()
        except Exception:
            continue
        final_url=canon(final_url)
        domain=domain_key(final_url)
        if not domain or domain in excluded_domains:
            continue
        info=source_info(final_url)
        if domain not in approved_primary_domains or not info.get('is_primary'):
            continue
        try:
            research_mode=research_access_mode(final_url)
        except Exception:
            continue
        candidates.append({
            'id':hashlib.sha256(final_url.encode()).hexdigest()[:20],
            'discovery_title':headline[:240],
            'source_url':final_url,
            'source_name':info.get('name') or domain,
            'category':category,
            'source_published_at':pub,
            'discovered_at':now_iso(),
            'source_terms_url':'',
            'discovery_summary':'',
            'status':'research_source',
            'research_mode':research_mode,
            'attempts':0
        })
        excluded_domains.add(domain)
        if len(candidates)>=limit:
            break
    return candidates

ACTIVE_QUEUE_STATUSES = ('READY','WRITING_PENDING','WRITTEN')
HEAVY_TERMINAL_FIELDS = ('evidence_pages','discovery_group','research_dossier')


def _queue_stamp(item):
    return str(item.get('prepared_at') or item.get('staged_at') or item.get('checked_at') or item.get('research_ready_at') or '')


def trim_research_queue(queue, max_size=None):
    """Bound the research queue WITHOUT ever dropping work that is still in progress.

    Candidates waiting to be written (WRITING_PENDING), written drafts (WRITTEN) and READY articles
    are always kept first. Only finished records (published, expired, rejected, held) compete for
    the remaining room, newest first. The old rule sorted by `prepared_at`, which freshly staged
    candidates do not have yet, so once the queue reached its cap every new candidate was cut in the
    same run that staged it and nothing was ever written or published.
    """
    max_size=max_size or MAX_RESEARCH_QUEUE
    items=[x for x in queue if isinstance(x,dict)]
    now=datetime.now(timezone.utc)

    def is_active(item):
        status=item.get('status')
        if status in ('READY','WRITING_PENDING'):
            return True
        if status=='WRITTEN':
            # A written staging record is only needed while its article can still be repaired or
            # published (freshness windows are 72h); older ones are finished records.
            stamp=as_utc(item.get('staged_at') or item.get('research_ready_at'))
            return stamp is None or now-stamp<timedelta(days=5)
        return False

    active=[x for x in items if is_active(x)]
    terminal=[x for x in items if not is_active(x)]
    active.sort(key=_queue_stamp,reverse=True)
    terminal.sort(key=_queue_stamp,reverse=True)
    kept_active=active[:max_size]
    kept_terminal=terminal[:max(0,max_size-len(kept_active))]
    for item in kept_terminal:
        # Finished records only need their outcome; the sealed pages are large and never reused.
        if item.get('status') in {'PUBLISHED','EXPIRED','REJECT','WRITTEN'}:
            for field in HEAVY_TERMINAL_FIELDS:
                item.pop(field,None)
    return kept_active+kept_terminal


def main():
    feeds=json.loads(FEEDS.read_text(encoding='utf-8'))
    active_articles=json.loads(ARTICLES.read_text(encoding='utf-8'))
    archive_articles=json.loads(ARCHIVE.read_text(encoding='utf-8')) if ARCHIVE.exists() else []
    catalog_path=ROOT/'data/archive_catalog.json'
    archive_catalog=json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else []
    published_records=archive_articles + archive_catalog + active_articles
    research_queue=json.loads(RESEARCH_QUEUE.read_text(encoding='utf-8')) if RESEARCH_QUEUE.exists() else []
    queued_records=[x.get('article',{}) for x in research_queue if isinstance(x,dict) and isinstance(x.get('article'),dict) and x.get('status')=='READY']
    articles=published_records + queued_records
    pending=json.loads(PENDING.read_text(encoding='utf-8')) if PENDING.exists() else []
    seen_data=json.loads(SEEN.read_text(encoding='utf-8')) if SEEN.exists() else {'items':{},'last_run':None}
    if isinstance(seen_data,list):
        seen_data={'items':{x.get('source_url'):x for x in seen_data if x.get('source_url')},'last_run':None}
    seen=seen_data.setdefault('items',{})
    run_started=datetime.now(timezone.utc)
    cursor_map=seen_data.setdefault('feed_cursors',{})
    if not cursor_map:
        bootstrap=as_utc(INITIAL_WINDOW_START)
        if bootstrap is None: raise ValueError('NEWS_INITIAL_WINDOW_START must be a valid ISO-8601 timestamp')
        cursor_map.update({f.get('id') or f.get('url'):bootstrap.isoformat() for f in feeds if f.get('enabled',False)})
        print(f'[WINDOW] First-run bootstrap starts at {bootstrap.isoformat()} (exclusive lower bound; articles must be newer).')
    source_usage=seen_data.setdefault('source_usage', [])
    recent_source_names=[x.get('source_name','') for x in source_usage[-12:] if x.get('source_name')]
    usage_counts={}
    for source_name in recent_source_names:
        usage_counts[source_name]=usage_counts.get(source_name,0)+1
    known_urls={canon(x.get('source_url','')) for x in published_records if x.get('source_url')}
    known_urls|={canon(x) for x in seen.keys()}
    known_urls|={canon(u) for a in queued_records for u in a.get('source_urls',[]) if u}
    known_titles=[x.get('title','') for x in published_records+queued_records]
    pending_urls={canon(x.get('source_url','')) for x in pending}
    found=[]; undated_items=[]; failures=0; successful_feeds=0; recovered_undated=0
    feed_domain_by_name={f.get('name'):domain_key(f.get('url','')) for f in feeds}
    for record in pending:
        if not record.get('source_feed_domain'):
            record['source_feed_domain']=feed_domain_by_name.get(record.get('source_name'),'')
    pending_by_url={canon(x.get('source_url','')):x for x in pending if x.get('source_url')}
    for feed in feeds:
        if not feed.get('enabled',False): continue
        feed_key=feed.get('id') or feed.get('url')
        cursor=as_utc(cursor_map.get(feed_key)) or as_utc(INITIAL_WINDOW_START)
        try:
            discovery_status=str(feed.get('discovery_access_status','UNVERIFIED')).upper()
            feed_mode=str(feed.get('status','')).lower()
            if discovery_status not in {'DISCOVERY_ALLOWED','DISCOVERY_ONLY'} or feed_mode not in {'discovery_only','discovery_allowed'}:
                print(f"[SKIP] Feed not explicitly configured for metadata-only discovery: {feed.get('name')}")
                continue
            if not robots_allowed(feed['url']):
                raise RuntimeError('robots.txt disallows feed access or could not be verified')
            payload=fetch(feed['url'],accept='application/rss+xml, application/atom+xml, application/xml, text/xml,*/*;q=0.5',limit=2_000_000)
            items=parse_feed(payload,feed)
            if not items:
                raise RuntimeError('RSS/Atom response parsed but contains no usable items')
            # Some publisher RSS entries omit dates or use non-standard fields.
            # Recover a real publication timestamp from page metadata for a small,
            # bounded sample; never substitute the discovery time.
            date_recovered=0
            for candidate in items:
                if not feed.get('recover_dates_from_article_metadata', False):
                    break
                if candidate.get('source_published_at') or date_recovered>=8:
                    continue
                date_recovered+=1
                try:
                    if not robots_allowed(candidate['source_url']):
                        continue
                    page_meta=fetch(candidate['source_url'],
                                    accept='text/html,application/xhtml+xml;q=0.9,*/*;q=0.5',
                                    limit=300_000)
                    recovered_date=publication_date_from_html(page_meta)
                    if recovered_date:
                        candidate['source_published_at']=recovered_date
                        candidate['date_source']='article_metadata'
                except Exception:
                    # Keep the item visible in pending with an undated status.
                    continue
            if date_recovered:
                recovered_count=sum(1 for x in items if x.get('date_source')=='article_metadata')
                print(f"[DATE] {feed['name']}: recovered {recovered_count} publication dates from article metadata (checked up to {date_recovered}).")
            successful_feeds+=1
            print(f"[OK] {feed['name']}: {len(items)} feed items; window ({cursor.isoformat()}, {run_started.isoformat()}]")
            for item in items:
                published_at=as_utc(item.get('source_published_at'))
                u=canon(item['source_url'])
                if published_at is None:
                    existing=pending_by_url.get(u)
                    if existing is None and seen.get(u,{}).get('status')!='needs_publication_date':
                        item['status']='needs_publication_date'
                        item['last_error']='RSS item has no valid publication date; it is retained but cannot enter automatic research.'
                        undated_items.append(item)
                        pending_by_url[u]=item
                        seen[u]={'id':item['id'],'source_url':u,'title':item['discovery_title'],
                                 'source_name':item['source_name'],'status':'needs_publication_date','seen_at':now_iso()}
                    print(f"[HOLD] Missing/invalid publication date retained outside research queue: {feed['name']} | {item['discovery_title'][:100]}")
                    continue
                existing=pending_by_url.get(u)
                if existing and existing.get('status')=='needs_publication_date':
                    existing.update(item)
                    existing['status']='queued'
                    existing.pop('last_error',None)
                    seen[u]={'id':item['id'],'source_url':u,'title':item['discovery_title'],
                             'source_name':item['source_name'],'status':'queued','seen_at':now_iso()}
                    recovered_undated+=1
                    continue
                if u in known_urls and seen.get(u,{}).get('status')=='needs_publication_date':
                    item['status']='queued'
                    found.append(item)
                    seen[u]={'id':item['id'],'source_url':u,'title':item['discovery_title'],
                             'source_name':item['source_name'],'status':'queued','seen_at':now_iso()}
                    recovered_undated+=1
                    continue
                if not is_in_window(item.get('source_published_at'), cursor, run_started):
                    continue
                if u in pending_urls or u in known_urls: continue
                if any(similarity(item['discovery_title'],t)>0.76 for t in known_titles):
                    seen[u]={'id':item['id'],'source_url':u,'title':item['discovery_title'],'status':'duplicate_title','seen_at':now_iso()}
                    continue
                found.append(item); pending_urls.add(u)
            cursor_map[feed_key]=run_started.isoformat()
        except Exception as e:
            failures+=1
            print(f"[WARN] Feed failed {feed.get('name')}; cursor retained at {cursor.isoformat()}: {type(e).__name__}: {e}")
    for x in found:
        u=canon(x['source_url'])
        seen[u]={'id':x['id'],'source_url':u,'title':x['discovery_title'],'source_name':x['source_name'],
                 'category':x['category'],'first_seen_at':now_iso(),'status':'queued'}
    pending.extend(undated_items)
    pending.extend(found)
    now=run_started
    queued=[]
    for item in pending:
        status=item.get('status','queued')
        retry_due=as_utc(item.get('retry_after'))
        if status=='queued' or (status in {'retry','HOLD'} and (retry_due is None or retry_due<=now)):
            queued.append(item)
    groups=[]
    for item in sorted(queued,key=lambda x:(x.get('source_published_at') or '',x.get('discovered_at') or ''),reverse=True):
        placed=False
        for group in groups:
            # Compare with the group's anchor, not every member. Transitive
            # chaining previously merged unrelated stories into one evidence set.
            if group and headlines_related(item['discovery_title'],group[0]['discovery_title']):
                group.append(item); placed=True; break
        if not placed: groups.append([item])
    from zoneinfo import ZoneInfo
    vn_today=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    daily_category_counts={category:0 for category in CATEGORY_LABELS}
    counted_ids=set()
    for existing in published_records:
        ident=str(existing.get('id') or '')
        if ident and ident in counted_ids: continue
        if ident: counted_ids.add(ident)
        pub=as_utc(existing.get('appnho_published_at') or existing.get('fetched_at') or existing.get('published_at'))
        if pub and pub.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date()==vn_today:
            category=existing.get('category')
            if category in daily_category_counts: daily_category_counts[category]+=1
    def group_rank(group):
        best=max(group,key=lambda x:source_score(x,len(group),usage_counts.get(x.get('source_name',''),0)*8))
        category=best.get('category')
        return (-daily_category_counts.get(category,0),
                source_score(best,len(group),usage_counts.get(best.get('source_name',''),0)*8),
                best.get('source_published_at') or '')
    groups.sort(key=group_rank,reverse=True)
    prepared=0; category_counts={}; generation_attempts=0; ai_responses=0; generation_failures=0
    candidate_groups_attempted=0
    for group in groups:
        if prepared>=MAX_NEW_PER_RUN or candidate_groups_attempted>=MAX_CANDIDATE_GROUPS_PER_RUN:
            break
        group.sort(key=lambda x:(source_score(x,len(group),usage_counts.get(x.get('source_name',''),0)*8),
                                 x.get('source_published_at') or ''),reverse=True)
        mainlead=group[0]
        category=mainlead.get('category')
        if category_counts.get(category,0)>=2:
            continue
        dt=as_utc(mainlead.get('source_published_at'))
        if dt and now-dt>timedelta(hours=72):
            for x in group:
                x['status']='stale'
            continue
        candidate_groups_attempted+=1
        evidence={}; good=[]; domains=set(); used_families=set()
        # RSS remains metadata-only. For factual research, retrieve bounded page
        # evidence from distinct publisher families under robots rules. Unreviewed
        # sources are tagged LIMITED_FACTUAL_REFERENCE and are never treated as
        # commercially licensed content or copied into the published article.
        for item in group[:10]:
            domain=domain_key(item.get('source_url',''))
            info=source_info(item.get('source_url',''))
            family=(info.get('source_family') or domain).casefold()
            if family and family in used_families:
                continue
            try:
                mode=research_access_mode(item['source_url'], item.get('source_feed_domain'))
                page=extract_page(item['source_url'], access_mode=mode)
                if (bool(str(page).strip())
                        and headlines_related(mainlead.get('discovery_title',''), item.get('discovery_title',''))
                        and evidence_matches_title(mainlead.get('discovery_title',''), page)
                        and evidence_matches_title(item.get('discovery_title',''), page)):
                    item['research_mode']=mode
                    evidence[item['source_url']]=page
                    good.append(item)
                    if family:
                        used_families.add(family)
                    if domain:
                        domains.add(domain)
            except Exception as e:
                print(f"[WARN] Publisher evidence unavailable: {item['source_name']} — {e}")
        # Search for original/official material using the supplied source directory.
        if len(domains)<2:
            official_candidates=search_official_sources(mainlead['discovery_title'],mainlead.get('category',''),domains,limit=6,
                                                       research_request=next((x.get('research_request','') for x in group if x.get('research_request')),''))
            for candidate in official_candidates:
                try:
                    if not robots_allowed(candidate['source_url']):
                        continue
                    page=extract_page(candidate['source_url'], access_mode=candidate.get('research_mode'))
                    if str(page).strip() and evidence_matches_title(candidate.get('discovery_title',''),page):
                        evidence[candidate['source_url']]=page
                        good.append(candidate)
                        domains.add(domain_key(candidate['source_url']))
                        print(f"[RESEARCH] Added primary-source evidence: {candidate['source_name']}")
                except Exception as e:
                    print(f"[INFO] Primary source unavailable: {candidate['source_name']} — {e}")
        source_refs=[]
        for item in good:
            info=source_info(item.get('source_url',''))
            source_refs.append({
                'url':item.get('source_url',''),
                'source_family':info.get('source_family') or domain_key(item.get('source_url','')),
                'is_primary':info['is_primary'],
                # Preflight only: make_article still verifies a matching core-claim
                # excerpt before persisting is_primary_for_claim on the article.
                'is_primary_for_claim':info['is_primary'],
                'research_mode':item.get('research_mode','LIMITED_FACTUAL_REFERENCE')
            })
        source_count,has_primary,_=source_independence(source_refs)
        dossier=build_research_dossier(good,evidence)
        ready_to_write, dossier_reason=research_dossier_ready(dossier)
        if not good or (source_count<2 and not has_primary) or not ready_to_write:
            reason=('Không đủ nguồn độc lập hoặc không truy cập được nội dung nguồn.'
                    if not good or (source_count<2 and not has_primary) else dossier_reason)
            mark_group_retry(group,reason,now)
            print(f"[RESEARCH_MORE] {mainlead['discovery_title']}: {reason}; retained for another research cycle.")
            continue
        # Only dossiers that pass the API-free factual-readiness gate enter Writing.
        queue_id=hashlib.sha256((mainlead.get('source_url','')+'|'+str(mainlead.get('discovery_title',''))).encode('utf-8')).hexdigest()[:20]
        group_urls={x.get('source_url') for x in group if x.get('source_url')}
        existing=next((x for x in research_queue if isinstance(x,dict) and
                       (str(x.get('queue_id'))==queue_id or
                        bool(group_urls.intersection(x.get('source_urls') or [])))),None)
        candidate={
            'queue_id':queue_id,'status':'WRITING_PENDING','staged_at':now_iso(),
            'expires_at':(now+timedelta(hours=72)).isoformat(),
            'category_hint':category,'lead_title':mainlead.get('discovery_title',''),
            'source_urls':[x.get('source_url','') for x in good if x.get('source_url')],
            'evidence_pages':evidence,'group':good,'discovery_group':group,
            'research_dossier':dossier,'research_ready_at':now_iso(),
            'research_readiness_reason':dossier_reason
        }
        if existing:
            if existing.get('status') in {'WRITTEN','READY','PUBLISHED'}:
                print(f"[SKIP] Candidate already has a completed article: {mainlead.get('discovery_title','')}")
                continue
            # Replace stale/held evidence with the newly collected, better dossier.
            existing.update(candidate)
            print(f"[RESEARCH_REFRESH] Updated dossier for {mainlead.get('discovery_title','')} ({dossier['distinct_fact_units']} fact units).")
        else:
            research_queue.append(candidate)
        prepared+=1
        category_counts[category]=category_counts.get(category,0)+1
        for item in group:
            item['status']='writing_pending'
            u=canon(item.get('source_url',''))
            seen.setdefault(u,{})['status']='writing_pending'
        print(f"[STAGED] {mainlead.get('discovery_title','')} ({len(good)} verified source(s)); waiting for writing workflow.")
    # Keep READY items until publication/expiry; preserve the newest usable queue records.
    research_queue=trim_research_queue(research_queue)
    def pending_priority(item):
        status=item.get('status','queued')
        active_status=status in {'queued','retry','HOLD','ready_for_publish'}
        stamp=as_utc(item.get('discovered_at') or item.get('first_seen_at'))
        return (0 if active_status else 1, -(stamp.timestamp() if stamp else 0))
    pending.sort(key=pending_priority)
    if len(pending)>MAX_PENDING:
        dropped=len(pending)-MAX_PENDING
        print(f"[WARN] Pending queue exceeded {MAX_PENDING}; trimming {dropped} oldest terminal/history records first.")
        pending=pending[:MAX_PENDING]
    seen_data['last_run']=now_iso()
    seen_data['last_run_stats']={
        'feeds_enabled':len([f for f in feeds if f.get('enabled')]),
        'feeds_eligible':len([f for f in feeds if f.get('enabled') and str(f.get('discovery_access_status','')).upper() in {'DISCOVERY_ALLOWED','DISCOVERY_ONLY'} and str(f.get('status','')).lower() in {'discovery_only','discovery_allowed'}]),
        'feeds_succeeded':successful_feeds,'new_leads_in_window':len(found),
        'prepared':prepared,'published':0,'feed_failures':failures,
        'undated_items_retained':len(undated_items),'undated_items_recovered':recovered_undated,
        'window_end_at':run_started.isoformat(),
        'bootstrap_start':INITIAL_WINDOW_START if not seen_data.get('last_successful_window_end') else None,
        'api_keys_configured':sum(bool(os.getenv(k,'').strip()) for k in ('GEMINI_API_KEY','CLOUDFLARE_API_TOKEN','OPENROUTER_API_KEY')),
        'generation_attempts':generation_attempts,'ai_responses':ai_responses,
        'generation_failures':generation_failures,'candidate_groups_attempted':candidate_groups_attempted,
        'ready_queue':sum(1 for x in research_queue if x.get('status')=='READY')
    }
    seen_data['last_run_window_end']=run_started.isoformat() if successful_feeds else seen_data.get('last_run_window_end')
    if len(seen)>20000:
        ranked=sorted(seen.items(),key=lambda kv:kv[1].get('seen_at') or kv[1].get('first_seen_at') or '',reverse=True)
        seen_data['items']=dict(ranked[:20000])
        seen=seen_data['items']
        print(f'[GITHUB] Dedup history bounded to {len(seen)} recent records.')
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    RESEARCH_QUEUE.write_text(json.dumps(research_queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    SEEN.write_text(json.dumps(seen_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"[RESEARCH] Prepared {prepared} candidates; ready queue={sum(1 for x in research_queue if x.get('status')=='READY')}; active published articles unchanged.")
    print(f"SUMMARY: new_leads={len(found)} prepared={prepared} ready_queue={sum(1 for x in research_queue if x.get('status')=='READY')} feed_failures={failures}")
if __name__ == '__main__':
    main()
