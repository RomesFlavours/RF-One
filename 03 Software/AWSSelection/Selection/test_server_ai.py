"""Server transport contract: explicit configuration and no secret/PII leaks or fallback."""
import os,sys,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import requests
HERE=Path(__file__).resolve().parent;sys.path[:0]=[str(HERE),str(HERE.parent/'RF-One Data Store')]
from workspace import rule_ai


class ServerAI(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'RFONE_SELECTION_RULE_AI_PROVIDER':'openai','RFONE_SELECTION_OPENAI_API_KEY':'private-test-key','RFONE_SELECTION_OPENAI_MODEL':'explicit-test-model'},clear=True);self.env.start()
    def tearDown(self):self.env.stop()
    def test_response_contract_and_no_retention(self):
        response=Mock(status_code=200);response.json.return_value={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"reply":"Ready","rule":null}'}]}]}
        with patch.object(rule_ai.requests,'post',return_value=response) as request:
            self.assertEqual(rule_ai.generate('Requested JSON'),{'reply':'Ready','rule':None})
            payload=request.call_args.kwargs['json'];self.assertFalse(payload['store']);self.assertNotIn('tools',payload);self.assertEqual(payload['model'],'explicit-test-model');self.assertFalse(request.call_args.kwargs['allow_redirects'])
    def test_malformed_top_level_is_rejected(self):
        response=Mock(status_code=200);response.json.return_value=[]
        with patch.object(rule_ai.requests,'post',return_value=response),self.assertRaises(RuntimeError):rule_ai.generate('JSON')

    def test_model_is_required(self):
        del os.environ['RFONE_SELECTION_OPENAI_MODEL']
        with patch.object(rule_ai.requests,'post') as request,self.assertRaises(RuntimeError):rule_ai.generate('JSON')
        request.assert_not_called()
    def test_error_has_no_body_or_key_and_no_fallback(self):
        response=Mock(status_code=401,text='private-test-key CV contents')
        with patch.object(rule_ai.requests,'post',return_value=response),patch.object(rule_ai,'transport') as local:
            with self.assertRaises(RuntimeError) as err:rule_ai.generate('CV contents')
            self.assertNotIn('private-test-key',str(err.exception));self.assertNotIn('CV contents',str(err.exception));local.assert_not_called()
    def test_timeout_does_not_retry(self):
        with patch.object(rule_ai.requests,'post',side_effect=requests.Timeout()) as request,self.assertRaises(RuntimeError):rule_ai.generate('JSON')
        self.assertEqual(request.call_count,1)
    def test_incomplete_is_not_a_rule(self):
        response=Mock(status_code=200);response.json.return_value={'status':'incomplete','output':[]}
        with patch.object(rule_ai.requests,'post',return_value=response),self.assertRaises(RuntimeError):rule_ai.generate('JSON')


if __name__=='__main__':unittest.main()
