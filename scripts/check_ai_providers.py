#!/usr/bin/env python3
"""Safe AI provider preflight: validate credentials and discover eligible models without generating content."""
import os, sys
from news_pipeline import discover_gemini_models, discover_xai_models, discover_openrouter_models
checks = [
    ('Gemini', 'GEMINI_API_KEY', discover_gemini_models),
    ('Grok/xAI', 'XAI_API_KEY', discover_xai_models),
    ('OpenRouter', 'OPENROUTER_API_KEY', discover_openrouter_models),
]
ready = 0
for label, env, discover in checks:
    if not os.getenv(env, '').strip():
        print(f'[FAIL] {label}: required environment variable is missing (secret was not passed to workflow).')
        continue
    try:
        models = discover()
        if not models:
            print(f'[FAIL] {label}: authentication may have succeeded, but no eligible free model is currently available.')
            continue
        print(f'[OK] {label}: key accepted; {len(models)} eligible model(s) discovered. First candidate: {models[0]}')
        ready += 1
    except Exception as exc:
        # Provider exceptions do not include key values; do not print environment values.
        print(f'[FAIL] {label}: {str(exc)[:220]}')
if ready == 0:
    print('[FATAL] No provider is ready. Do not run automatic publishing until this is fixed.')
    sys.exit(1)
print(f'[SUMMARY] {ready}/3 providers ready. This check only validates authentication/model discovery; it does not generate or publish an article.')
