# Tips AI: OpenAI through private Amazon Bedrock

Product Owner instruction, 2026-11-09: replace failing direct Anthropic access
for Tips, update AWS and the local copy, push the change; no NAT and no database
alignment. The existing private `bedrock-runtime` endpoint remains in use.

Tips rule authoring calls the existing AI abstraction's `generate_json_for_tips`.
Its dedicated settings do not change Selection or Bank provider choices:

```text
RFONE_TIPS_AI_PROVIDER=BEDROCK
RFONE_TIPS_BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0
AWS_REGION=us-east-1
```

Local development additionally sets `RFONE_TIPS_AWS_PROFILE=rfone-dev-login` in
the ignored root `.env`. AWS does not set this profile: the App Runner instance
role supplies credentials. Neither environment needs an Anthropic/OpenAI API key.
OpenAI GPT-OSS 120B is the selected OpenAI model hosted on Bedrock; this is not
a request to the public ChatGPT/OpenAI API. There is no automatic provider fallback.

Converse returns final text alongside optional reasoning blocks. Only final text
is parsed as a JSON object; truncated/invalid replies remain unavailable outcomes.
Existing rule validation and explicit operator confirmation are unchanged.

## Release and rollback

1. Run `test_tips_openai_provider.py`, `test_ai_client_provider_selection.py`,
   and the synthetic Tips rule-authoring suite. No real business DB is involved.
2. Commit/push only this provider change. How-Works: technical — provider and
   credentials repair, no operational page, workflow, rule semantics or help change.
3. Overlay the two changed runtime Python files from that commit onto the exact
   source archive of the currently deployed Tips image. Preserve all other live
   files and the migration guard. Build/push a unique image tag using the existing
   `rfone-tips-build` project; do not overwrite the previous image tag.
4. Attach `openai-bedrock-policy.json` as `rfone-tips-openai-bedrock` to the existing
   App Runner instance role. It allows only InvokeModel on the selected model.
5. Update only Tips' image and the two dedicated AI environment variables.
   Preserve runtime secrets, VPC connector, networking and all other settings.
6. Verify the deployment operation and a real rule-interpretation POST without
   confirming/saving the proposed rule. Store release IDs and rollback references.

Rollback: restore the recorded previous image and previous runtime environment,
then remove only the new inline policy if no longer needed. No schema migration,
data import, DB synchronization, new gateway or new database is part of this release.

References: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-openai.html
