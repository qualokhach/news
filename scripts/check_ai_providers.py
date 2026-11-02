#!/usr/bin/env python3
"""Validate AI credentials/model discovery; optionally send a tiny real generation probe."""
import argparse, os, sys
from urllib.parse import urlencode
import news_pipeline as pipeline

CLOUDFLARE_MODEL = '@cf/meta/llama-3.3-70b-instruct-fp8-fast'

PROVIDERS = [
    ('Gemini', 'GEMINI_API_KEY', pipeline.discover_gemini_models),
    ('Grok/xAI', 'XAI_API_KEY', pipeline.discover_xai_models),
    ('OpenRouter', 'OPENROUTER_API_KEY', pipeline.discover_openrouter_models),
]

def cloudflare_live_probe():
    """Send one tiny inference request to the configured Cloudflare Workers AI model."""
    account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID', '').strip()
    token = os.getenv('CLOUDFLARE_API_TOKEN', '').strip()
    if not account_id or not token:
        raise RuntimeError('CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is missing')
    endpoint = (
        'https://api.cloudflare.com/client/v4/accounts/'
        + account_id + '/ai/run/' + CLOUDFLARE_MODEL
    )
    payload = {
        'messages': [
            {'role': 'system', 'content': 'Reply briefly and exactly as requested.'},
            {'role': 'user', 'content': 'Reply with exactly: OK'}
        ],
        'max_tokens': 8,
        'temperature': 0
    }
    data = pipeline._post_json(
        endpoint, payload,
        {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        'Cloudflare Workers AI'
    )
    result = data.get('result') if isinstance(data, dict) else None
    output = result.get('response', '') if isinstance(result, dict) else ''
    if not output and isinstance(result, dict):
        output = result.get('output_text', '')
    if not output:
        raise RuntimeError('model returned an empty response or an unexpected response format')
    return str(output).strip()[:80]

def live_probe(label, model):
    """One short generation request. Grok may incur a small API charge."""
    if label == 'Gemini':
        key=os.getenv('GEMINI_API_KEY','').strip()
        endpoint='https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent?'+urlencode({'key':key})
        payload={'contents':[{'role':'user','parts':[{'text':'Reply with exactly: OK'}]}],
                 'generationConfig':{'temperature':0,'maxOutputTokens':8}}
        data=pipeline._post_json(endpoint,payload,{'Content-Type':'application/json'},'Gemini probe')
        parts=data.get('candidates',[{}])[0].get('content',{}).get('parts',[])
        output=''.join(x.get('text','') for x in parts if isinstance(x,dict)).strip()
    else:
        env='XAI_API_KEY' if label=='Grok/xAI' else 'OPENROUTER_API_KEY'
        headers={'Authorization':'Bearer '+os.getenv(env,'').strip(),'Content-Type':'application/json'}
        if label=='Grok/xAI':
            endpoint='https://api.x.ai/v1/responses'
            payload={'model':model,'input':'Reply with exactly: OK','max_output_tokens':8,'store':False}
            data=pipeline._post_json(endpoint,payload,headers,label+' probe')
            output=''.join(
                content.get('text','')
                for item in data.get('output',[]) if isinstance(item,dict) and item.get('type')=='message'
                for content in (item.get('content') or []) if isinstance(content,dict) and content.get('type')=='output_text'
            ).strip()
        else:
            endpoint='https://openrouter.ai/api/v1/chat/completions'
            headers.update({'HTTP-Referer':'https://appnho.io.vn/','X-Title':'AppNho News'})
            payload={'model':model,'messages':[{'role':'user','content':'Reply with exactly: OK'}],
                     'temperature':0,'max_tokens':8}
            data=pipeline._post_json(endpoint,payload,headers,label+' probe')
            choices=data.get('choices') or []
            output=(choices[0].get('message') or {}).get('content','') if choices else ''
            if isinstance(output,list):
                output=''.join(x.get('text','') for x in output if isinstance(x,dict))
            output=str(output).strip()
    if not output:
        raise RuntimeError('model returned an empty response')
    return output[:80]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live-probe',action='store_true',
                        help='Send one short real generation request to the first eligible model of every configured provider.')
    args=parser.parse_args()
    ready=0
    configured=0
    probe_ok=0
    for label, env, discover in PROVIDERS:
        if not os.getenv(env,'').strip():
            print(f'[SKIP] {label}: key is not configured.')
            continue
        configured+=1
        try:
            models=discover()
            if not models:
                print(f'[FAIL] {label}: key/model discovery returned no eligible model.')
                continue
            model=models[0]
            print(f'[OK] {label}: authenticated model catalog; {len(models)} eligible model(s). Selected: {model}')
            ready+=1
            if args.live_probe:
                try:
                    response=live_probe(label,model)
                    print(f'[LIVE PASS] {label}/{model}: response received ({response!r})')
                    probe_ok+=1
                except Exception as exc:
                    print(f'[LIVE FAIL] {label}/{model}: {str(exc)[:220]}')
        except Exception as exc:
            print(f'[FAIL] {label}: {str(exc)[:220]}')
    cf_account = os.getenv('CLOUDFLARE_ACCOUNT_ID', '').strip()
    cf_token = os.getenv('CLOUDFLARE_API_TOKEN', '').strip()
    if cf_account or cf_token:
        configured += 1
        if not (cf_account and cf_token):
            print('[FAIL] Cloudflare Workers AI: both Account ID and API Token are required.')
        elif args.live_probe:
            try:
                response = cloudflare_live_probe()
                print(f'[LIVE PASS] Cloudflare Workers AI/{CLOUDFLARE_MODEL}: response received ({response!r})')
                probe_ok += 1
                ready += 1
            except Exception as exc:
                print(f'[LIVE FAIL] Cloudflare Workers AI/{CLOUDFLARE_MODEL}: {str(exc)[:220]}')
        else:
            print('[OK] Cloudflare Workers AI: Account ID and API Token are configured; live probe not requested.')
            ready += 1
    if ready==0:
        print('[FATAL] No AI provider is ready. Automatic research cannot generate candidates.')
        return 1
    if args.live_probe and probe_ok==0:
        print('[FATAL] No provider passed a real generation probe.')
        return 1
    if args.live_probe:
        print(f'[SUMMARY] {probe_ok}/{configured} configured providers passed a real generation probe.')
    else:
        print(f'[SUMMARY] {ready}/3 providers passed authentication and model discovery.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
