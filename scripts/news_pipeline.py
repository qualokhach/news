#!/usr/bin/env python3
"""AppNho News pipeline: discover, deduplicate, score, draft with a three-provider AI fallback chain, validate, publish.

Only public RSS metadata and publicly accessible article pages are used as factual leads.
The source text is used for fact-checking context, not reproduced. If the AI key is missing,
new leads remain queued and no articles are published.
"""
import os, re, json, html, hashlib, urllib.request, urllib.error, difflib, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ROOT / 'config/feeds.json'
ARTICLES = ROOT / 'data/articles.json'
ARCHIVE = ROOT / 'data/archive_articles.json'
PENDING = ROOT / 'data/pending.json'
SEEN = ROOT / 'data/seen_items.json'
TIMEOUT = 8
UA = 'AppNhoNewsBot/1.0 (+https://github.com/qualokhach/news)'
MAX_NEW_PER_RUN = int(os.getenv('MAX_ARTICLES_PER_RUN', '4'))
MAX_PENDING = 5000
# Optional model overrides are honored only when explicitly configured. By default, discover
# currently available models at runtime and prefer lightweight/high-quota free candidates.
GEMINI_MODEL = os.getenv('GEMINI_MODEL', '').strip()
GROK_MODEL = os.getenv('GROK_MODEL', '').strip()
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', '').strip()
THUMBS = {
    'world': 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_gioi.png',
    'vietnam': 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Viet_Nam.png',
    'sports': 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_thao.png',
    'technology': 'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Cong_Nghe.png',
}
CATEGORY_LABELS = {'world':'Thế giới','vietnam':'Việt Nam','sports':'Thể thao','technology':'Công nghệ'}
STOP = set('và là của có cho trong với một những các được từ đến khi tại về theo sau trước đang đã sẽ này đó như nhưng vì để nếu thì hoặc cũng vào hơn rất nhiều người ngày năm tháng tin bài thông tin'.split())


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
    for name in names:
        n = node.find(name)
        if n is not None and n.text: return n.text.strip()
    return ''
def parse_date(raw):
    if not raw: return ''
    try:
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            d = datetime.fromisoformat(raw.replace('Z','+00:00'))
            if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc).isoformat()
        except Exception: return ''
def fetch(url, accept='text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', limit=1_500_000):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if r.status != 200: raise RuntimeError(f'HTTP {r.status}')
        return r.read(limit)
def canon(url):
    url = (url or '').strip()
    url = re.sub(r'#.*$', '', url)
    # Strip common tracking parameters without changing article identity parameters.
    url = re.sub(r'([?&])(utm_[^=&]+|fbclid|gclid)=[^&]*', '', url, flags=re.I)
    url = url.rstrip('?&')
    return url.rstrip('/')
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
        date=get_text(node,['pubDate','published','updated',f'{atom}published',f'{atom}updated'])
        description=clean(get_text(node,['description','summary',f'{atom}summary','{http://purl.org/rss/1.0/modules/content/}encoded']))
        link=canon(link)
        if not title or not link.startswith(('https://','http://')): continue
        uid=hashlib.sha256(link.encode()).hexdigest()[:20]
        out.append({'id':uid,'discovery_title':title[:240],'source_url':link,'source_name':feed['name'],
                    'category':feed['category'],'source_published_at':parse_date(date),'discovered_at':now_iso(),
                    'source_terms_url':feed.get('terms_url',''),'discovery_summary':description[:1200],'status':'queued','attempts':0})
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
def extract_page(url):
    raw=fetch(url, limit=2_000_000)
    text=raw.decode('utf-8','replace')
    p=TextExtractor()
    try: p.feed(text)
    except Exception: pass
    lines=[re.sub(r'\s+',' ',x).strip() for x in ''.join(p.parts).splitlines()]
    lines=[x for x in lines if len(x)>35]
    # Remove cookie, subscription, and common UI noise; keep only a bounded factual excerpt.
    cleaned=[]; seen=set()
    for line in lines:
        low=line.lower()
        if any(x in low for x in ['accept all cookies','subscribe to our newsletter','sign up to our','advertisement','đăng ký nhận tin','đọc thêm','xem thêm']): continue
        if line not in seen: cleaned.append(line); seen.add(line)
    return '\n'.join(cleaned)[:9000]

def tokens(s):
    return {x.lower() for x in re.findall(r'[\wÀ-ỹ]{3,}', s or '', flags=re.UNICODE) if x.lower() not in STOP}
def similarity(a,b):
    ta,tb=tokens(a),tokens(b)
    jac=len(ta&tb)/max(1,len(ta|tb))
    seq=difflib.SequenceMatcher(None,(a or '').lower(),(b or '').lower()).ratio()
    return max(jac,seq*0.72)
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
def parse_ai_json(txt):
    txt=(txt or '').strip()
    txt=re.sub(r'^```(?:json)?\s*|\s*```$', '', txt, flags=re.I)
    # Some OpenAI-compatible models wrap JSON in a short explanation; extract the outer object safely.
    if not txt.startswith('{'):
        a=txt.find('{'); b=txt.rfind('}')
        if a >= 0 and b > a: txt=txt[a:b+1]
    obj=json.loads(txt)
    if not isinstance(obj, dict): raise ValueError('AI response is not a JSON object')
    required={'publish','title','summary','category','seo_title','meta_description','keywords','body','source_index'}
    missing=required-set(obj)
    if missing: raise ValueError('AI response missing fields: '+', '.join(sorted(missing)))
    if not isinstance(obj.get('body'), list) or not isinstance(obj.get('keywords'), list):
        raise ValueError('AI response body/keywords have wrong types')
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
    if GEMINI_MODEL: return [GEMINI_MODEL]
    data=get_json('https://generativelanguage.googleapis.com/v1beta/models?key='+key,provider='Gemini')
    # Google's live model list does not expose per-account free-tier eligibility. Keep a
    # conservative allowlist of models currently documented with free-tier pricing, then
    # intersect it with models actually returned for this key. Update this list after reviewing pricing docs.
    free_names={'gemini-3.1-flash-lite','gemini-2.5-flash-lite'}
    candidates=[]
    for m in data.get('models',[]):
        name=m.get('name','').removeprefix('models/')
        methods=m.get('supportedGenerationMethods',[])
        if not name or 'generateContent' not in methods or name not in free_names: continue
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
    """Discover the explicitly approved Grok model(s) from the xAI API.

    The GitHub secret keeps its existing name GROK_API_APPNHO_NEWS; the workflow
    maps it to XAI_API_KEY. We never call Groq and never guess a model that the
    xAI account did not return.
    """
    key = os.getenv('XAI_API_KEY', '').strip()
    if not key:
        return []
    data = get_json('https://api.x.ai/v1/models', {'Authorization': 'Bearer ' + key}, 'Grok/xAI')
    rows = data.get('data', []) if isinstance(data, dict) else []
    available = {str(m.get('id', '')).strip() for m in rows if isinstance(m, dict)}
    approved = [GROK_MODEL] if GROK_MODEL else ['grok-4.1-fast-non-reasoning']
    return [model for model in approved if model and model in available]

def discover_openrouter_models():
    key=os.getenv('OPENROUTER_API_KEY','').strip()
    if not key: return []
    if OPENROUTER_MODEL: return [OPENROUTER_MODEL]
    data=get_json('https://openrouter.ai/api/v1/models',{'Authorization':'Bearer '+key},'OpenRouter')
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
        try: context=int(m.get('context_length') or 0)
        except (TypeError,ValueError): context=0
        if context and context < 12000: continue
        low=mid.lower()
        # Favor general text/instruct models and moderate model sizes; avoid vision-only models.
        score=0
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
        'Bạn là biên tập viên tin tức tiếng Việt. Viết độc lập, chính xác, dễ đọc, không phóng đại. '
        'Chỉ dùng dữ kiện có trong bằng chứng được cung cấp. Không bịa số liệu, phát biểu, nguyên nhân, '
        'dự báo hoặc trích dẫn. Không sao chép câu chữ nguồn. Nếu bằng chứng không đủ, trả về JSON với publish=false. '
        'Không nhồi từ khóa, không lặp ý để kéo dài. Output chỉ JSON hợp lệ, không markdown.')}]},
        'contents':[{'role':'user','parts':[{'text':prompt}]}],
        'generationConfig':{'temperature':0.25,'responseMimeType':'application/json','maxOutputTokens':7000}}
    data=_post_json(endpoint,payload,{'Content-Type':'application/json'},'Gemini/'+model)
    parts=data.get('candidates',[{}])[0].get('content',{}).get('parts',[])
    txt=''.join(p.get('text','') for p in parts).strip()
    if not txt: raise RuntimeError('Gemini returned empty content or blocked output')
    return parse_ai_json(txt)

def openai_compatible(prompt, provider, key_env, endpoint, model, extra_headers=None, json_mode=True):
    key=os.getenv(key_env,'').strip()
    if not key: raise RuntimeError(f'{provider} key missing')
    headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'}
    headers.update(extra_headers or {})
    payload={'model':model,'messages':[
        {'role':'system','content':('Bạn là biên tập viên tin tức tiếng Việt. Viết độc lập, chính xác, không phóng đại; '
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

def generate_with_fallback(prompt):
    """Discover current models and try a bounded list per provider, using free models only."""
    providers=[]
    for name, env, discover, call in [
        ('Gemini','GEMINI_API_KEY',discover_gemini_models,lambda model: gemini(prompt,model)),
        ('Grok','XAI_API_KEY',discover_xai_models,lambda model: openai_compatible(prompt,'Grok/xAI','XAI_API_KEY','https://api.x.ai/v1/chat/completions',model)),
        ('OpenRouter','OPENROUTER_API_KEY',discover_openrouter_models,lambda model: openai_compatible(prompt,'OpenRouter','OPENROUTER_API_KEY','https://openrouter.ai/api/v1/chat/completions',model,{'HTTP-Referer':'https://appnho.io.vn/','X-Title':'AppNho News'},json_mode=False))]:
        if not os.getenv(env,'').strip():
            print(f'[SKIP] {name}: key not configured'); continue
        try:
            models=discover()
            if not models:
                print(f'[WARN] {name}: no currently eligible models discovered'); continue
            # Cap model probes to keep each run bounded. Prefer first-ranked low-cost/free candidates.
            providers.append((name,models[:5],call))
            print(f'[MODEL] {name}: discovered {len(models)} eligible model(s); will probe up to {min(5,len(models))}')
        except Exception as e:
            print(f'[WARN] {name} model discovery failed: {str(e)[:180]}')
            # If live discovery fails, do not guess a model unless user explicitly pinned one.
    errors=[]
    for name, models, call in providers:
        for model in models:
            try:
                result=call(model)
                if result.get('publish'):
                    body=[clean(x) for x in result.get('body',[]) if clean(x)]
                    words=word_count(' '.join(body))
                    if len(body)<6 or words<600:
                        raise ValueError(f'Generated draft failed minimum content check ({words} words, {len(body)} paragraphs)')
                    if result.get('category') not in CATEGORY_LABELS:
                        raise ValueError('Generated draft has invalid category')
                print(f'[AI] Response received from {name} model={model}')
                return result, name+':'+model
            except Exception as e:
                message=str(e)
                key=os.getenv({'Gemini':'GEMINI_API_KEY','Grok':'XAI_API_KEY','OpenRouter':'OPENROUTER_API_KEY'}[name],'')
                if key: message=message.replace(key,'[redacted]')
                message=message[:180]
                errors.append(f'{name}/{model}: {message}')
                print(f'[WARN] {name} model unavailable/invalid; trying next eligible model ({message})')
                # A long delay is not useful for quota errors; next model/provider is the fallback.
                time.sleep(0.4)
    raise RuntimeError('All discovered free/eligible AI models failed: '+' | '.join(errors[-12:] or ['no configured provider/model']))

def make_prompt(group, evidence):
    lead=group[0]
    sources=[{'name':x['source_name'],'url':x['source_url'],'published_at':x.get('source_published_at',''),'headline':x['discovery_title'],'page_evidence':evidence.get(x['source_url'],'')[:5000]} for x in group[:3]]
    return '''Hãy đánh giá sự kiện và tạo một bài tin mới cho AppNho News. Trả về JSON có đúng các trường:
{"publish":true/false,"reason":"...","title":"...","summary":"...","category":"world|vietnam|sports|technology","published_at":"ISO-8601 UTC","seo_title":"...","meta_description":"...","keywords":["..."],"body":["đoạn 1", "đoạn 2"],"source_index":0}
Quy tắc:
- Chỉ publish=true nếu dữ kiện đủ rõ, sự kiện đáng tin, không phải tin trùng và có ích. Nếu không chắc, publish=false.
- Viết tiếng Việt tự nhiên, bài khoảng 650-900 từ (ít nhất 600 từ), 7-10 đoạn có nội dung khác nhau: sự kiện chính, dữ kiện đã xác minh, bối cảnh, tác động/ý nghĩa chỉ khi có căn cứ, điều cần theo dõi. Không lặp ý, không tự bịa bối cảnh.
- Không chép lại câu chữ bài nguồn; diễn đạt độc lập. Không dùng mô tả RSS làm nội dung. Không tạo lời dẫn giả, số liệu giả hoặc quote giả.
- Nếu nguồn mâu thuẫn hoặc chỉ có tiêu đề mà không có bằng chứng trong nội dung trang, publish=false.
- SEO: tiêu đề tự nhiên, từ khóa cụ thể, mô tả không quá 160 ký tự, 5-8 keyword phù hợp. Không nhồi từ khóa.
- category phải là một trong bốn giá trị cho sẵn và đúng nội dung.
- published_at dùng ngày công bố của nguồn chính; nếu không xác định được, dùng thời điểm hiện tại UTC.
- source_index là chỉ số (0-based) của nguồn chính trong danh sách bằng chứng.
- Không thêm trường khác. JSON thuần.

Đầu mối được nhóm theo sự kiện (nhiều nguồn có thể cùng nói về một việc):
''' + json.dumps(sources,ensure_ascii=False)

def make_article(obj, group):
    if not obj.get('publish'): return None
    title=clean(obj.get('title',''))
    summary=clean(obj.get('summary',''))
    category=obj.get('category','')
    body=obj.get('body',[])
    if category not in CATEGORY_LABELS or not title or len(body)<6: return None
    body=[clean(p) for p in body if clean(p)]
    full=' '.join(body)
    if word_count(full)<600: raise ValueError(f'Generated article too short: {word_count(full)} words')
    # Reject obvious boilerplate repetition.
    norm=[re.sub(r'\W+',' ',p.lower()).strip() for p in body]
    if len(set(norm))<max(4,len(norm)-2): raise ValueError('Generated body contains repeated paragraphs')
    if sum(len(p) for p in body)<2500: raise ValueError('Generated article lacks substance')
    idx=obj.get('source_index',0)
    try: main=group[int(idx)]
    except Exception: main=group[0]
    pub=obj.get('published_at') or main.get('source_published_at') or now_iso()
    try:
        d=datetime.fromisoformat(pub.replace('Z','+00:00'))
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        pub=d.astimezone(timezone.utc).isoformat()
    except Exception: pub=main.get('source_published_at') or now_iso()
    ident=slugify(title)
    # IDs are unique and stable; avoid duplicate events by title similarity checks before calling this.
    ident=ident[:72]+'-'+hashlib.sha1((main['source_url']+title).encode()).hexdigest()[:8]
    keywords=[clean(x)[:60] for x in obj.get('keywords',[]) if clean(x)][:8]
    if len(keywords)<4: keywords=list(dict.fromkeys(keywords+[title.split(':')[0],CATEGORY_LABELS[category],'tin tức '+CATEGORY_LABELS[category].lower()]))[:5]
    return {'id':ident,'title':title,'summary':summary[:360],'category':category,
        'source_name':main['source_name'],'source_url':main['source_url'],'published_at':pub,
        'fetched_at':now_iso(),'content_type':'ai_assisted_independent_editorial','collection':'current',
        'body':body,'editorial_note':'Bài được tạo tự động từ các dữ kiện công khai đã được hệ thống thu thập; cần sửa nếu phát hiện sai sót.',
        'generation_provider':obj.get('_provider',''),
        'seo_title':clean(obj.get('seo_title') or title)[:70],
        'meta_description':clean(obj.get('meta_description') or summary)[:160],
        'keywords':keywords,'slug':ident,'images':[],
        'content_image_url':'','content_image_alt':'','content_image_credit':'','content_image_credit_url':'',
        'word_count':word_count(full),'display_source':True,'source_urls':list(dict.fromkeys(x['source_url'] for x in group[:3])),
        'source_links':list(dict.fromkeys(x['source_url'] for x in group[:3] if x['source_url'] != main['source_url']))}

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
        if not any(x in license_name.lower() for x in ['cc by','cc0','public domain','pdm']): continue
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

def main():
    feeds=json.loads(FEEDS.read_text(encoding='utf-8'))
    # GitHub is the canonical store: articles, pending queue, and deduplication state
    # are committed back to this repository by the workflow after this script succeeds.
    active_articles=json.loads(ARTICLES.read_text(encoding='utf-8'))
    archive_articles=json.loads(ARCHIVE.read_text(encoding='utf-8')) if ARCHIVE.exists() else []
    catalog_path=ROOT/'data/archive_catalog.json'
    archive_catalog=json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else []
    articles=archive_articles + archive_catalog + active_articles
    # Catalog entries are metadata-only; they participate in duplicate checks, not mutation.
    pending=json.loads(PENDING.read_text(encoding='utf-8')) if PENDING.exists() else []
    seen_data=json.loads(SEEN.read_text(encoding='utf-8')) if SEEN.exists() else {'items':{},'last_run':None}
    original_ids={str(a.get('id')) for a in articles if a.get('id')}
    if isinstance(seen_data,list): seen_data={'items':{x.get('source_url'):x for x in seen_data if x.get('source_url')},'last_run':None}
    seen=seen_data.setdefault('items',{})
    # Window boundaries are stored per feed. A failed feed keeps its previous cursor,
    # allowing it to catch up next run without blocking healthy feeds.
    run_started=datetime.now(timezone.utc)
    cursor_map=seen_data.setdefault('feed_cursors',{})
    if not cursor_map:
        bootstrap=as_utc(INITIAL_WINDOW_START)
        if bootstrap is None: raise ValueError('NEWS_INITIAL_WINDOW_START must be a valid ISO-8601 timestamp')
        cursor_map.update({f.get('id') or f.get('url'):bootstrap.isoformat() for f in feeds if f.get('enabled',False)})
        print(f'[WINDOW] First-run bootstrap starts at {bootstrap.isoformat()} (exclusive lower bound; articles must be newer).')
    source_usage=seen_data.setdefault('source_usage', [])
    # Only successful publications count toward source diversity; failed runs do not.
    recent_source_names=[x.get('source_name','') for x in source_usage[-12:] if x.get('source_name')]
    usage_counts={}
    for source_name in recent_source_names: usage_counts[source_name]=usage_counts.get(source_name,0)+1
    known_urls={canon(x.get('source_url','')) for x in articles if x.get('source_url')}
    known_titles=[x.get('title','') for x in articles]
    known_urls|={canon(x) for x in seen.keys()}
    pending_urls={canon(x.get('source_url','')) for x in pending}
    found=[]; failures=0; successful_feeds=0
    for feed in feeds:
        if not feed.get('enabled',False): continue
        feed_key=feed.get('id') or feed.get('url')
        cursor=as_utc(cursor_map.get(feed_key)) or as_utc(INITIAL_WINDOW_START)
        try:
            payload=fetch(feed['url'],accept='application/rss+xml, application/atom+xml, application/xml, text/xml,*/*;q=0.5',limit=2_000_000)
            items=parse_feed(payload,feed)
            successful_feeds+=1
            print(f"[OK] {feed['name']}: {len(items)} feed items; window ({cursor.isoformat()}, {run_started.isoformat()}]")
            for item in items:
                published_at=as_utc(item.get('source_published_at'))
                # Do not treat undated entries as fresh. Leave them unmarked so a later
                # valid feed entry can still be discovered; emit an explicit diagnostic.
                if published_at is None:
                    print(f"[SKIP] Missing/invalid publication date: {feed['name']} | {item['discovery_title'][:100]}")
                    continue
                if not is_in_window(item.get('source_published_at'), cursor, run_started):
                    continue
                u=canon(item['source_url'])
                if u in pending_urls or u in known_urls: continue
                # Prevent obvious title duplicates against already published stories.
                if any(similarity(item['discovery_title'],t)>0.76 for t in known_titles):
                    seen[u]={'id':item['id'],'source_url':u,'title':item['discovery_title'],'status':'duplicate_title','seen_at':now_iso()}; continue
                found.append(item); pending_urls.add(u)
            # Advance only this feed after a successful HTTP fetch and XML parse. The cursor
            # and newly queued items are persisted together at the end of this workflow step.
            cursor_map[feed_key]=run_started.isoformat()
        except Exception as e:
            failures+=1; print(f"[WARN] Feed failed {feed.get('name')}; cursor retained at {cursor.isoformat()}: {type(e).__name__}: {e}")
    # Save discovery history before editorial processing; dedupe by canonical URL.
    for x in found:
        u=canon(x['source_url']); seen[u]={'id':x['id'],'source_url':u,'title':x['discovery_title'],'source_name':x['source_name'],'category':x['category'],'first_seen_at':now_iso(),'status':'queued'}
    pending.extend(found)
    # Group pending items by similar headlines to cross-check the same event across feeds.
    queued=[x for x in pending if x.get('status','queued')=='queued' and int(x.get('attempts',0))<3]
    groups=[]
    for item in sorted(queued,key=lambda x: (x.get('source_published_at') or '',x.get('discovered_at') or ''),reverse=True):
        placed=False
        for g in groups:
            if any(similarity(item['discovery_title'],y['discovery_title'])>=0.34 for y in g):
                g.append(item); placed=True; break
        if not placed: groups.append([item])
    # Prioritize categories with the fewest articles published today (Vietnam time),
    # then freshness/corroboration. This is a preference, not a reason to publish weak news.
    from zoneinfo import ZoneInfo
    vn_today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    daily_category_counts = {category: 0 for category in CATEGORY_LABELS}
    counted_article_ids = set()
    for existing in articles:
        existing_id = str(existing.get('id') or '')
        # archive_catalog mirrors archived records; count each published article only once.
        if existing_id and existing_id in counted_article_ids:
            continue
        if existing_id:
            counted_article_ids.add(existing_id)
        published_at = as_utc(existing.get('published_at'))
        if published_at and published_at.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date() == vn_today:
            category = existing.get('category')
            if category in daily_category_counts:
                daily_category_counts[category] += 1
    # Prioritize newer items, multi-source corroboration and category balance.
    def group_rank(g):
        # Prefer a fresh corroborated story, but penalize publishers used in recent
        # successful runs so the front page does not repeatedly favor one outlet.
        best=max(g, key=lambda x: source_score(x,len(g),usage_counts.get(x.get('source_name',''),0)*8))
        category = best.get('category')
        # Deficit rank gives a meaningful preference to underrepresented categories.
        deficit = -daily_category_counts.get(category, 0)
        return (deficit, source_score(best,len(g),usage_counts.get(best.get('source_name',''),0)*8), best.get('source_published_at') or '')
    groups.sort(key=group_rank,reverse=True)
    api_keys_present=any(os.getenv(k,'').strip() for k in ('GEMINI_API_KEY','XAI_API_KEY','OPENROUTER_API_KEY'))
    published=0; used_categories=set(); processed_urls=set(); generation_attempts=0; ai_responses=0; generation_failures=0
    if not api_keys_present:
        print('[INFO] No AI API keys configured: discovery only; no article will be published.')
    else:
        for group in groups:
            if published>=MAX_NEW_PER_RUN: break
            # Prefer category diversity per run.
            # Choose the lead source by freshness plus recent source-usage balance.
            # A recently used source can still win if its report is materially newer.
            group.sort(key=lambda x: (source_score(x,len(group),usage_counts.get(x.get('source_name',''),0)*8), x.get('source_published_at') or ''), reverse=True)
            mainlead=group[0]
            if mainlead.get('category') in used_categories and len(used_categories)<4: continue
            # Ignore old leads in the current-news stream; historical content is handled separately.
            dt=mainlead.get('source_published_at')
            if dt:
                try:
                    age=datetime.now(timezone.utc)-datetime.fromisoformat(dt.replace('Z','+00:00'))
                    if age>timedelta(hours=72):
                        for x in group: x['status']='stale'; processed_urls.add(canon(x['source_url']))
                        continue
                except Exception: pass
            evidence={}; good=[]
            for x in group[:3]:
                try:
                    page=extract_page(x['source_url'])
                    if len(page)>500: evidence[x['source_url']]=page; good.append(x)
                except Exception as e: print(f"[WARN] Article page unavailable: {x['source_name']} — {e}")
            if not good:
                mainlead['attempts']=int(mainlead.get('attempts',0))+1
                if mainlead['attempts']>=3: mainlead['status']='needs_manual_review'
                continue
            try:
                generation_attempts+=1
                result, provider_name=generate_with_fallback(make_prompt(good,evidence))
                ai_responses+=1
                if not result.get('publish'):
                    for x in group: x['status']='rejected_quality'; x['editorial_reason']=clean(result.get('reason','Not enough verified evidence'))[:300]; processed_urls.add(canon(x['source_url']))
                    for x in group:
                        u=canon(x['source_url']); seen.setdefault(u,{})['status']='rejected_quality'
                    print(f"[REJECT] {mainlead['discovery_title']}: {result.get('reason','quality gate')}")
                    continue
                result['_provider']=provider_name
                article=make_article(result,good)
                if article: article['origin']='auto'
                if not article: raise ValueError('AI output failed article validation')
                image=find_licensed_image(article)
                if image:
                    article['content_image_url']=image['url']
                    article['content_image_alt']=image['alt']
                    article['content_image_credit']=image['credit'] + ' (' + image['license'] + ')'
                    article['content_image_credit_url']=image['credit_url']
                    article['content_image_license_url']=image['license_url']
                if any(similarity(article['title'],a.get('title',''))>0.70 for a in articles):
                    for x in group: x['status']='duplicate_event'; processed_urls.add(canon(x['source_url']))
                    continue
                # The repository JSON is the source of truth. IDs are checked before append.
                if any(str(x.get('id')) == str(article.get('id')) for x in articles):
                    for x in group:
                        x['status']='duplicate_id'; processed_urls.add(canon(x['source_url']))
                    print(f"[SKIP] Duplicate article ID: {article['id']}")
                    continue
                articles.append(article)
                active_articles.append(article)
                published+=1; used_categories.add(article['category']); daily_category_counts[article['category']] = daily_category_counts.get(article['category'], 0) + 1
                source_usage.append({'source_name':article.get('source_name',''),'source_url':article.get('source_url',''),'category':article.get('category',''),'article_id':article.get('id'),'published_at':article.get('published_at'),'recorded_at':now_iso()})
                source_usage=source_usage[-200:]
                seen_data['source_usage']=source_usage
                usage_counts[article.get('source_name','')]=usage_counts.get(article.get('source_name',''),0)+1
                for x in group:
                    x['status']='published' if x['source_url']==article['source_url'] else 'cross_checked_same_event'
                    x['article_id']=article['id']; processed_urls.add(canon(x['source_url']))
                    u=canon(x['source_url']); seen.setdefault(u,{})['status']=x['status']; seen[u]['article_id']=article['id']
                print(f"[PUBLISHED] {article['title']} ({article['word_count']} words, {article['category']})")
                time.sleep(1.2)
            except Exception as e:
                generation_failures+=1
                mainlead['attempts']=int(mainlead.get('attempts',0))+1
                mainlead['last_error']=str(e)[:300]
                if mainlead['attempts']>=3: mainlead['status']='needs_manual_review'
                print(f"[WARN] Generation skipped for '{mainlead['discovery_title']}': {e}")
    # Persist and cap files; never discard queued items without status.
    pending.sort(key=lambda x: x.get('discovered_at',''),reverse=True)
    pending=pending[:MAX_PENDING]
    seen_data['last_run']=now_iso(); seen_data['last_run_stats']={'feeds_enabled':len([f for f in feeds if f.get('enabled')]),'feeds_succeeded':successful_feeds,'new_leads_in_window':len(found),'published':published,'feed_failures':failures,'window_end_at':run_started.isoformat(),'bootstrap_start':INITIAL_WINDOW_START if not seen_data.get('last_successful_window_end') else None,'api_keys_configured':sum(bool(os.getenv(k,'').strip()) for k in ('GEMINI_API_KEY','XAI_API_KEY','OPENROUTER_API_KEY')),'generation_attempts':generation_attempts,'ai_responses':ai_responses,'generation_failures':generation_failures}
    seen_data['last_run_window_end']=run_started.isoformat() if successful_feeds else seen_data.get('last_run_window_end')
    # Retain recent source URLs so deduplication stays bounded without silently losing all history.
    if len(seen)>20000:
        ranked=sorted(seen.items(), key=lambda kv: kv[1].get('seen_at') or kv[1].get('first_seen_at') or '', reverse=True)
        seen_data['items']=dict(ranked[:20000])
        seen=seen_data['items']
        print(f'[GITHUB] Dedup history bounded to {len(seen)} recent records.')
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ARTICLES.write_text(json.dumps(active_articles,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    SEEN.write_text(json.dumps(seen_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'[GITHUB] Saved {len(active_articles)} active articles; immutable archive files unchanged; archive catalog entries: {len(archive_catalog)}; queue and dedup history saved.')
    print(f"SUMMARY: new_leads={len(found)} published={published} pending={sum(1 for x in pending if x.get('status','queued')=='queued')} feed_failures={failures}")
if __name__=='__main__': main()
