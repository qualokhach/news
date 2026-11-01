"""Operational regression tests for discovery permissions, health checks and schedule safety."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch
import audit_feeds
import check_run_health
import news_pipeline

ROOT=Path(__file__).resolve().parents[1]

class MetadataOnlyDiscoveryTests(unittest.TestCase):
    def test_configured_feeds_are_metadata_only_and_not_research_approved(self):
        feeds=json.loads((ROOT/'config/feeds.json').read_text(encoding='utf-8'))
        self.assertTrue(feeds)
        for feed in feeds:
            self.assertTrue(feed.get('enabled'))
            self.assertEqual(feed.get('status'),'discovery_only')
            self.assertTrue(feed.get('terms_url'))
            self.assertNotIn('commercial_use_approved',feed)

    def test_rss_parser_keeps_metadata_not_publisher_excerpt(self):
        xml=b'''<?xml version="1.0"?><rss version="2.0"><channel><item><title>Headline</title><link>https://publisher.example/story</link><pubDate>Sat, 31 Oct 2026 08:00:00 GMT</pubDate><description>Full publisher summary text that must not be retained.</description></item></channel></rss>'''
        feed={'name':'Example RSS','category':'world','url':'https://publisher.example/rss'}
        item=news_pipeline.parse_feed(xml,feed)[0]
        self.assertEqual(item['discovery_title'],'Headline')
        self.assertEqual(item['discovery_summary'],'')
        self.assertEqual(item['discovery_mode'],'metadata_only')
        self.assertEqual(item['source_feed_domain'],'publisher.example')

    def test_feed_audit_skips_disabled_feed_without_network(self):
        feed={'name':'Disabled','url':'https://example.com/rss','enabled':False}
        with patch('audit_feeds.urllib.request.urlopen') as request:
            result=audit_feeds.check(feed)
        request.assert_not_called()
        self.assertEqual(result['status'],'disabled')

    def test_feed_audit_fetches_and_parses_enabled_rss_endpoint(self):
        from unittest.mock import MagicMock
        feed={
            'name':'Allowed metadata','url':'https://example.com/rss','category':'world','enabled':True,
            'status':'discovery_only','discovery_access_status':'DISCOVERY_ONLY'
        }
        response=MagicMock()
        response.__enter__.return_value=response
        response.status=200
        response.read.return_value=b'<rss><channel><item><title>Headline</title></item></channel></rss>'
        with patch('audit_feeds.robots_allowed',return_value=True), \
             patch('audit_feeds.urllib.request.urlopen',return_value=response) as request:
            result=audit_feeds.check(feed)
        request.assert_called_once()
        self.assertEqual(result['status'],'metadata_only_ok')
        self.assertEqual(result['items'],1)

    def test_empty_or_unusable_feed_does_not_advance_success_count(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=root/"data"; cfg=root/"config"
            data.mkdir(); cfg.mkdir()
            feed={"name":"Empty","url":"https://publisher.example/rss","category":"world",
                  "enabled":True,"status":"discovery_only","discovery_access_status":"DISCOVERY_ONLY"}
            (cfg/"feeds.json").write_text(json.dumps([feed]),encoding="utf-8")
            for name,content in {
                "articles.json":"[]","archive_articles.json":"[]","pending.json":"[]",
                "research_queue.json":"[]","seen_items.json":'{"items":{}}',
                "archive_catalog.json":"[]"
            }.items():
                (data/name).write_text(content,encoding="utf-8")
            with patch.object(news_pipeline,"ROOT",root), \
                 patch.object(news_pipeline,"FEEDS",cfg/"feeds.json"), \
                 patch.object(news_pipeline,"ARTICLES",data/"articles.json"), \
                 patch.object(news_pipeline,"ARCHIVE",data/"archive_articles.json"), \
                 patch.object(news_pipeline,"PENDING",data/"pending.json"), \
                 patch.object(news_pipeline,"SEEN",data/"seen_items.json"), \
                 patch.object(news_pipeline,"RESEARCH_QUEUE",data/"research_queue.json"), \
                 patch.object(news_pipeline,"robots_allowed",return_value=True), \
                 patch.object(news_pipeline,"fetch",return_value=b"<rss><channel></channel></rss>"), \
                 patch.dict(os.environ,{},clear=True):
                news_pipeline.main()
            stats=json.loads((data/"seen_items.json").read_text(encoding="utf-8"))["last_run_stats"]
            self.assertEqual(stats["feeds_succeeded"],0)
            self.assertEqual(stats["feed_failures"],1)

    def test_undated_rss_item_is_retained_but_never_sent_to_research(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/"data"; cfg=root/"config"
            data.mkdir(); cfg.mkdir()
            feed={"name":"Undated","url":"https://publisher.example/rss","category":"world",
                  "enabled":True,"status":"discovery_only","discovery_access_status":"DISCOVERY_ONLY"}
            (cfg/"feeds.json").write_text(json.dumps([feed]),encoding="utf-8")
            for name,content in {
                "articles.json":"[]","archive_articles.json":"[]","pending.json":"[]",
                "research_queue.json":"[]","seen_items.json":'{"items":{}}',
                "archive_catalog.json":"[]"
            }.items():
                (data/name).write_text(content,encoding="utf-8")
            rss=b"<rss><channel><item><title>Undated public event</title><link>https://publisher.example/story</link></item></channel></rss>"
            with patch.object(news_pipeline,"ROOT",root), \
                 patch.object(news_pipeline,"FEEDS",cfg/"feeds.json"), \
                 patch.object(news_pipeline,"ARTICLES",data/"articles.json"), \
                 patch.object(news_pipeline,"ARCHIVE",data/"archive_articles.json"), \
                 patch.object(news_pipeline,"PENDING",data/"pending.json"), \
                 patch.object(news_pipeline,"SEEN",data/"seen_items.json"), \
                 patch.object(news_pipeline,"RESEARCH_QUEUE",data/"research_queue.json"), \
                 patch.object(news_pipeline,"robots_allowed",return_value=True), \
                 patch.object(news_pipeline,"fetch",return_value=rss), \
                 patch.dict(os.environ,{},clear=True):
                news_pipeline.main()
            pending=json.loads((data/"pending.json").read_text(encoding="utf-8"))
            stats=json.loads((data/"seen_items.json").read_text(encoding="utf-8"))["last_run_stats"]
            self.assertEqual(len(pending),1)
            self.assertEqual(pending[0]["status"],"needs_publication_date")
            self.assertEqual(stats["undated_items_retained"],1)
            self.assertEqual(json.loads((data/"research_queue.json").read_text(encoding="utf-8")),[])

    def test_pipeline_main_completes_metadata_only_discovery_without_publishing_unverified_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=root/'data'; data.mkdir()
            feed={
                'name':'Example RSS','url':'https://publisher.example/rss','category':'world',
                'enabled':True,'status':'discovery_only','discovery_access_status':'DISCOVERY_ONLY',
                'terms_status':'UNVERIFIED','commercial_use_status':'UNVERIFIED'
            }
            (root/'config').mkdir()
            (root/'config/feeds.json').write_text(json.dumps([feed]),encoding='utf-8')
            (data/'articles.json').write_text('[]',encoding='utf-8')
            (data/'archive_articles.json').write_text('[]',encoding='utf-8')
            (data/'pending.json').write_text('[]',encoding='utf-8')
            (data/'research_queue.json').write_text('[]',encoding='utf-8')
            (data/'seen_items.json').write_text('{"items":{},"last_run":null}',encoding='utf-8')
            (data/'archive_catalog.json').write_text('[]',encoding='utf-8')
            now=datetime.now(timezone.utc)
            rss=(f'<rss version="2.0"><channel><item><title>Test headline for metadata discovery</title>'
                 f'<link>https://publisher.example/story</link><pubDate>{format_datetime(now)}</pubDate>'
                 '<description>Publisher text that must not be retained.</description></item></channel></rss>').encode()
            robots_patch=patch.object(news_pipeline,'robots_allowed',return_value=True)
            patches=[
                patch.object(news_pipeline,'ROOT',root),
                patch.object(news_pipeline,'FEEDS',root/'config/feeds.json'),
                patch.object(news_pipeline,'ARTICLES',data/'articles.json'),
                patch.object(news_pipeline,'ARCHIVE',data/'archive_articles.json'),
                patch.object(news_pipeline,'PENDING',data/'pending.json'),
                patch.object(news_pipeline,'SEEN',data/'seen_items.json'),
                patch.object(news_pipeline,'RESEARCH_QUEUE',data/'research_queue.json'),
                robots_patch,
                patch.object(news_pipeline,'fetch',return_value=rss),
                patch.dict(os.environ,{},clear=True),
            ]
            with patches[0],patches[1],patches[2],patches[3],patches[4],patches[5],patches[6],patches[7] as robots_mock,patches[8],patches[9]:
                news_pipeline.main()
            pending=json.loads((data/'pending.json').read_text(encoding='utf-8'))
            seen=json.loads((data/'seen_items.json').read_text(encoding='utf-8'))
            self.assertEqual(len(pending),1)
            self.assertEqual(pending[0]['discovery_summary'],'')
            self.assertEqual(pending[0]['discovery_mode'],'metadata_only')
            self.assertEqual(seen['last_run_stats']['feeds_succeeded'],1)
            self.assertEqual(seen['last_run_stats']['prepared'],0)
            self.assertGreaterEqual(robots_mock.call_count,1, 'The configured RSS endpoint must be checked.')
            self.assertEqual(json.loads((data/'articles.json').read_text(encoding='utf-8')),[])

class RunHealthTests(unittest.TestCase):
    def test_discovery_only_idle_run_is_healthy_if_feeds_and_provider_worked(self):
        errors,notes=check_run_health.evaluate({'feeds_enabled':50,'feeds_eligible':50,'feeds_succeeded':38,'api_keys_configured':2,'prepared':0,'generation_attempts':0,'ai_responses':0})
        self.assertEqual(errors,[])
        self.assertTrue(any("Feed coverage is degraded" in x for x in notes))

    def test_low_feed_coverage_is_not_green(self):
        errors,_=check_run_health.evaluate({'feeds_enabled':50,'feeds_eligible':50,'feeds_succeeded':10,'api_keys_configured':2})
        self.assertTrue(any("below the 50% minimum" in x for x in errors))

    def test_all_feeds_failed_is_not_green(self):
        errors,_=check_run_health.evaluate({'feeds_enabled':50,'feeds_eligible':50,'feeds_succeeded':0,'api_keys_configured':2})
        self.assertTrue(any('Every eligible' in x for x in errors))

    def test_no_provider_key_does_not_fail_api_free_research(self):
        errors,_=check_run_health.evaluate({'feeds_enabled':50,'feeds_eligible':50,'feeds_succeeded':36,'api_keys_configured':0,'prepared':4,'generation_attempts':0,'ai_responses':0})
        self.assertEqual(errors,[])


class WorkflowSafetyTests(unittest.TestCase):
    def test_build_workflow_has_expected_vietnam_publication_windows(self):
        text=(ROOT/'.github/workflows/build-news.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:',text)
        cron_lines=[line.strip() for line in text.splitlines() if line.strip().startswith('- cron:')]
        self.assertEqual(cron_lines,[
            '- cron: "45 22 * * *" # 05:45 Vietnam',
            '- cron: "45 4 * * *"  # 11:45 Vietnam',
            '- cron: "45 9 * * *"  # 16:45 Vietnam',
        ])

    def test_digest_runs_only_on_the_dedicated_noon_schedule(self):
        text=(ROOT/'.github/workflows/build-news.yml').read_text(encoding='utf-8')
        from resolve_publish_slot import resolve_slot
        self.assertIn('45 4 * * *',text)
        self.assertIn("steps.slot.outputs.slot_kind == 'digest'",text)
        self.assertIn('python scripts/create_digest.py',text)
        self.assertEqual(resolve_slot('schedule','45 4 * * *')['slot_kind'],'digest')
        self.assertEqual(resolve_slot('schedule','45 4 * * *')['max_articles'],'0')
        self.assertEqual(resolve_slot('schedule','45 22 * * *')['slot_kind'],'regular')
        self.assertEqual(resolve_slot('schedule','45 9 * * *')['slot_kind'],'regular')

    def test_research_workflow_runs_before_publication_windows(self):
        text=(ROOT/'.github/workflows/research-news.yml').read_text(encoding='utf-8')
        self.assertIn('45 21 * * *',text)
        self.assertIn('45 3 * * *',text)
        self.assertIn('45 8 * * *',text)
        self.assertIn('NEWS_PUBLIC_FACTUAL_RESEARCH: "1"',text)
        self.assertNotIn('GEMINI_API_KEY',text)
        self.assertNotIn('XAI_API_KEY',text)
        self.assertNotIn('OPENROUTER_API_KEY',text)
        self.assertNotIn('check_ai_providers.py',text)
        publish=(ROOT/'.github/workflows/build-news.yml').read_text(encoding='utf-8')
        self.assertIn('python scripts/write_candidates.py',publish)

    def test_research_pipeline_has_one_main_entrypoint_only(self):
        import re
        source=(ROOT/'scripts/news_pipeline.py').read_text(encoding='utf-8')
        guards=re.findall(r"^if __name__\s*==\s*['\\\"]__main__['\\\"]",source,re.M)
        self.assertEqual(len(guards),1)

    def test_both_workflows_run_the_same_offline_test_suite(self):
        for name in ('build-news.yml','research-news.yml'):
            text=(ROOT/'.github/workflows'/name).read_text(encoding='utf-8')
            self.assertIn("python -m unittest discover -s scripts -p 'test_*.py' -v",text)

if __name__=='__main__':
    unittest.main(verbosity=2)
