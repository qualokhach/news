import json, os, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from unittest.mock import patch
import write_candidates

class WritingStageTests(unittest.TestCase):
    def test_writing_stage_converts_staged_evidence_to_ready_article(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            queue=base/'research_queue.json'
            articles=base/'articles.json'
            archive=base/'archive_articles.json'
            seen=base/'seen_items.json'
            staged={
                'queue_id':'staged-1','status':'WRITING_PENDING',
                'staged_at':'2026-11-01T10:00:00+00:00',
                'expires_at':'2026-11-04T10:00:00+00:00',
                'lead_title':'A verified test headline',
                'group':[{'source_url':'https://www.bbc.co.uk/news/story-a','source_name':'BBC',
                          'discovery_title':'A verified test headline','source_published_at':'2026-11-01T09:00:00+00:00'},
                         {'source_url':'https://www.reuters.com/world/story-a','source_name':'Reuters',
                          'discovery_title':'A verified test headline','source_published_at':'2026-11-01T09:00:00+00:00'}],
                'evidence_pages':{'https://www.bbc.co.uk/news/story-a':'A verified test headline. Evidence text sufficiently long for the mocked writing stage. '*8,
                                  'https://www.reuters.com/world/story-a':'A verified test headline. Evidence text sufficiently long for the mocked writing stage. '*8},
                'discovery_group':[]
            }
            queue.write_text(json.dumps([staged]),encoding='utf-8')
            articles.write_text('[]',encoding='utf-8')
            archive.write_text('[]',encoding='utf-8')
            seen.write_text('{"items":{}}',encoding='utf-8')
            article={'id':'article-1','title':'A distinct researched article','body':['p1','p2','p3','p4'],
                     'source_urls':['https://source.example/story'],'freshness_ttl_hours':24}
            with patch.object(write_candidates,'QUEUE',queue), \
                 patch.object(write_candidates,'ARTICLES',articles), \
                 patch.object(write_candidates,'ARCHIVE',archive), \
                 patch.object(write_candidates,'SEEN',seen), \
                 patch.object(write_candidates.np,'make_prompt',return_value='prompt'), \
                 patch.object(write_candidates.np,'generate_with_fallback',
                              side_effect=lambda prompt,validator=None: (
                                  (validator({'publish':True},'Gemini:test-model') if validator else None) or
                                  ({'publish':True},'Gemini:test-model'))), \
                 patch.object(write_candidates.np,'make_article',return_value=article), \
                 patch.object(write_candidates.np,'find_licensed_image',return_value=None), \
                 patch.dict(os.environ,{'GEMINI_API_KEY':'test-key','MAX_ARTICLES_PER_SLOT':'1'},clear=False):
                write_candidates.main()
            result=json.loads(queue.read_text(encoding='utf-8'))
            ready=[x for x in result if x.get('status')=='READY']
            self.assertEqual(len(ready),1)
            self.assertEqual(ready[0]['article']['id'],'article-1')
            self.assertEqual(result[0]['status'],'WRITTEN')

if __name__=='__main__':
    unittest.main()
