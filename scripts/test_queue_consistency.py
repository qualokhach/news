import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import content_quality as cq
import repair_queue
import write_candidates


class NumericSupportTests(unittest.TestCase):
    LEDGER=[{'claim':'FIFA mở tài liệu cho hội đồng.','source_claim':'Members were told material will be released.',
             'evidence_snippet':'Members were told material will be released.',
             'evidence_by_source':[{'source_url':'u','snippet':'Questions covered the past 12 months.'}]}]

    def test_number_in_verified_snippet_is_accepted_without_source_pages(self):
        body=['UEFA nêu nhiều vấn đề trong 12 tháng qua.']
        self.assertEqual(cq.validate_body_fact_coverage(body,self.LEDGER),[])

    def test_unsupported_number_is_still_rejected(self):
        errors=cq.validate_body_fact_coverage(['Có 77 người liên quan.'],self.LEDGER)
        self.assertTrue(errors and '77' in errors[0])

    def test_numbers_verified_at_writing_time_are_honoured_later(self):
        pages={'u':'The scheme cost 12 million.'}
        body=['Dự án trị giá 12 triệu.']
        verified=cq.compute_verified_numbers(body,[],pages)
        self.assertEqual(verified,['12'])
        self.assertTrue(cq.validate_body_fact_coverage(body,[]))
        self.assertEqual(cq.validate_body_fact_coverage(body,[],verified_numbers=verified),[])

    def test_verified_numbers_never_include_unsupported_numbers(self):
        self.assertEqual(cq.compute_verified_numbers(['Có 77 và 12.'],[],{'u':'only 12 here'}),['12'])


class RepairQueueTests(unittest.TestCase):
    def queue(self):
        return [
            {'queue_id':'a','status':'WRITTEN','written_article_id':'a','evidence_pages':{'u':'12'}},
            {'queue_id':'a','status':'READY','article':{'id':'a','body':['12'],'fact_ledger':[]}},
            {'queue_id':'ok','status':'READY','article':{'id':'ok','verified_numbers':[]}},
        ]

    def test_invalid_ready_is_withdrawn_and_returned_to_writing(self):
        q=self.queue()
        with patch.object(repair_queue,'ready_candidate_errors',side_effect=lambda a:['lỗi'] if a['id']=='a' else []):
            repaired,withdrawn=repair_queue.repair(q)
        self.assertEqual(withdrawn,['a']); self.assertEqual(repaired,[])
        self.assertEqual(q[1]['status'],'REJECT')
        self.assertEqual(q[0]['status'],'WRITING_PENDING')
        self.assertNotIn('written_article_id',q[0])
        self.assertEqual(q[2]['status'],'READY')

    def test_ready_is_repaired_from_sealed_pages_when_only_numbers_were_missing(self):
        q=self.queue()
        def errors(article):
            return [] if (article.get('verified_numbers') or article['id']=='ok') else ['số liệu']
        with patch.object(repair_queue,'ready_candidate_errors',side_effect=errors):
            repaired,withdrawn=repair_queue.repair(q)
        self.assertEqual(repaired,['a'])
        self.assertEqual(withdrawn,[])
        self.assertEqual(q[1]['status'],'READY')
        self.assertEqual(q[1]['article']['verified_numbers'],['12'])


class WriteAttemptCapTests(unittest.TestCase):
    def test_hopeless_candidate_is_closed_after_max_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            files={n:base/n for n in ('q.json','a.json','ar.json','s.json')}
            item={'queue_id':'x','status':'WRITING_PENDING','staged_at':'2026-11-01T10:00:00+00:00',
                  'expires_at':'2099-01-01T00:00:00+00:00','lead_title':'t','write_attempts':write_candidates.MAX_WRITE_ATTEMPTS-1,
                  'group':[{'source_url':'https://www.bbc.co.uk/a','source_name':'BBC','discovery_title':'t'},
                           {'source_url':'https://www.reuters.com/a','source_name':'R','discovery_title':'t'}],
                  'evidence_pages':{'https://www.bbc.co.uk/a':'text '*50,'https://www.reuters.com/a':'text '*50}}
            files['q.json'].write_text(json.dumps([item]),encoding='utf-8')
            for n in ('a.json','ar.json'): files[n].write_text('[]',encoding='utf-8')
            files['s.json'].write_text('{"items":{}}',encoding='utf-8')
            with patch.object(write_candidates,'QUEUE',files['q.json']), patch.object(write_candidates,'ARTICLES',files['a.json']), \
                 patch.object(write_candidates,'ARCHIVE',files['ar.json']), patch.object(write_candidates,'SEEN',files['s.json']), \
                 patch.object(write_candidates,'PENDING',base/'p.json'), \
                 patch.object(write_candidates.np,'make_prompt',return_value='p'), \
                 patch.object(write_candidates.np,'generate_with_fallback',side_effect=RuntimeError('boom')), \
                 patch.dict(os.environ,{'GEMINI_API_KEY':'k'},clear=False):
                write_candidates.main()
            self.assertEqual(json.loads(files['q.json'].read_text(encoding='utf-8'))[0]['status'],'REJECT')


if __name__=='__main__':
    unittest.main()
