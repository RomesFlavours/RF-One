"""Tips OpenAI-on-Bedrock routing: no real credentials, DB or network."""
import os,unittest
from unittest.mock import Mock,patch
from rfone_data_store.selection.parsing import ai_client as ai

class OpenAITipsTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'RFONE_AI_PROVIDER':'ANTHROPIC','AWS_REGION':'us-east-1'},clear=True)
        self.reader=patch.object(ai,'_read_env_or_dotenv',side_effect=os.environ.get)
        self.env.start();self.reader.start()
        self.addCleanup(self.env.stop);self.addCleanup(self.reader.stop)

    def response(self,text='{"outcome":"PROPOSED"}',stop='end_turn'):
        return {'stopReason':stop,'output':{'message':{'content':[
            {'reasoningContent':{'reasoningText':{'text':'private reasoning'}}},{'text':text}]}}}

    @patch('boto3.client')
    def test_default_tips_routes_to_openai_without_changing_other_consumers(self,client):
        client.return_value.converse.return_value=self.response()
        self.assertEqual(ai.generate_json_for_tips('JSON rule')['outcome'],'PROPOSED')
        self.assertEqual(ai._active_provider(),'ANTHROPIC')
        self.assertEqual(client.return_value.converse.call_args.kwargs['modelId'],'openai.gpt-oss-120b-1:0')
        self.assertEqual(client.call_args.args[0],'bedrock-runtime')

    @patch('boto3.Session')
    def test_local_profile_and_model_are_explicit(self,session):
        os.environ['RFONE_TIPS_AWS_PROFILE']='configured-local-profile'
        os.environ['RFONE_TIPS_BEDROCK_MODEL_ID']='openai.gpt-oss-20b-1:0'
        session.return_value.client.return_value.converse.return_value=self.response()
        ai.generate_json_for_tips('JSON rule')
        session.assert_called_once_with(profile_name='configured-local-profile')
        self.assertEqual(session.return_value.client.return_value.converse.call_args.kwargs['modelId'],'openai.gpt-oss-20b-1:0')

    @patch('boto3.client')
    def test_reasoning_is_not_parsed_as_json(self,client):
        client.return_value.converse.return_value=self.response('```json\n{"ok":true}\n```')
        self.assertEqual(ai.generate_json_for_tips('JSON'),{'ok':True})

    @patch('boto3.client')
    def test_truncated_malformed_and_nonobject_responses_fail(self,client):
        for text,stop in [('{"ok":true}','max_tokens'),('not json','end_turn'),('[]','end_turn')]:
            client.return_value.converse.return_value=self.response(text,stop)
            with self.assertRaises(ai.AIProviderUnavailable):ai.generate_json_for_tips('JSON')

    @patch('boto3.client')
    def test_invalid_provider_or_nonopenai_model_never_calls_network(self,client):
        os.environ['RFONE_TIPS_AI_PROVIDER']='ANTHROPIC'
        with self.assertRaises(ai.AIProviderUnavailable):ai.generate_json_for_tips('JSON')
        os.environ['RFONE_TIPS_AI_PROVIDER']='BEDROCK';os.environ['RFONE_TIPS_BEDROCK_MODEL_ID']='anthropic.other'
        with self.assertRaises(ai.AIProviderUnavailable):ai.generate_json_for_tips('JSON')
        client.assert_not_called()

    @patch('boto3.client')
    def test_aws_error_is_reported_without_other_provider_fallback(self,client):
        from botocore.exceptions import ClientError
        client.return_value.converse.side_effect=ClientError({'Error':{'Code':'AccessDeniedException','Message':'not authorized'}},'Converse')
        with self.assertRaises(ai.AIProviderUnavailable):ai.generate_json_for_tips('JSON')
        self.assertEqual(client.return_value.converse.call_count,1)

if __name__=='__main__':unittest.main(verbosity=2)
