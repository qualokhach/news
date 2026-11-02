import os, unittest
from unittest.mock import patch
import check_ai_providers

class ProviderProbeTests(unittest.TestCase):
    def test_gemini_probe_calls_generate_content_and_reads_text(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-key'}), \
             patch.object(check_ai_providers.pipeline,'_post_json',return_value={
                 'candidates':[{'content':{'parts':[{'text':'OK'}]}}]
             }) as post:
            self.assertEqual(check_ai_providers.live_probe('Gemini','gemini-3.5-flash-lite'),'OK')
            self.assertIn(':generateContent?',post.call_args.args[0])
            self.assertEqual(post.call_args.args[1]['generationConfig']['maxOutputTokens'],8)

    def test_grok_probe_uses_primary_responses_api(self):
        with patch.dict(os.environ,{'XAI_API_KEY':'test-key'}), \
             patch.object(check_ai_providers.pipeline,'_post_json',return_value={
                 'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}]
             }) as post:
            self.assertEqual(check_ai_providers.live_probe('Grok/xAI','grok-current-model'),'OK')
            self.assertEqual(post.call_args.args[0],'https://api.x.ai/v1/responses')
            self.assertFalse(post.call_args.args[1]['store'])

    def test_openrouter_probe_uses_free_model_id(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key'}), \
             patch.object(check_ai_providers.pipeline,'_post_json',return_value={
                 'choices':[{'message':{'content':'OK'}}]
             }) as post:
            self.assertEqual(check_ai_providers.live_probe('OpenRouter','provider/model:free'),'OK')
            self.assertEqual(post.call_args.args[0],'https://openrouter.ai/api/v1/chat/completions')
            self.assertEqual(post.call_args.args[1]['model'],'provider/model:free')

    def test_cloudflare_probe_uses_account_token_and_selected_workers_ai_model(self):
        with patch.dict(os.environ, {
            'CLOUDFLARE_ACCOUNT_ID': 'account-test',
            'CLOUDFLARE_API_TOKEN': 'token-test'
        }), patch.object(check_ai_providers.pipeline, '_post_json', return_value={
            'success': True, 'result': {'response': 'OK'}
        }) as post:
            self.assertEqual(check_ai_providers.cloudflare_live_probe(), 'OK')
            self.assertIn('/accounts/account-test/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast', post.call_args.args[0])
            self.assertEqual(post.call_args.args[2]['Authorization'], 'Bearer token-test')
            self.assertEqual(post.call_args.args[1]['max_tokens'], 8)

if __name__=='__main__':
    unittest.main(verbosity=2)
