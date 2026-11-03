"""Isolated test: independent invoice reading with a vision-capable model on Amazon Bedrock.

Sends only the oriented original page (whole + overlapping top/bottom crops) plus prompt_used.txt. No Textract output,
no prior transcriptions, no expected values are given to the model.
"""
import datetime
import json
import os
import pathlib
import sys

import boto3
from botocore.config import Config

HERE = pathlib.Path(__file__).parent
IMG_DIR = pathlib.Path(sys.argv[1])
# Opus 5 / 5.5 / Sonnet 5 / Opus 4.7-4.8 are not enabled on this account.
# USD per 1M tokens (input, output) at Anthropic list price; Bedrock billing may differ.
PRICES = {"us.anthropic.claude-opus-4-6-v1": (5.00, 25.00), "us.anthropic.claude-sonnet-4-6": (3.00, 15.00)}
MODEL_ID = os.environ.get("VISION_MODEL_ID", "us.anthropic.claude-opus-4-6-v1")
REGION = "us-east-1"
MAX_TOKENS = 11000  # keeps worst-case cost of 3 calls under USD 1
PRICE_IN, PRICE_OUT = PRICES[MODEL_ID]

prompt = (HERE / "prompt_used.txt").read_text(encoding="utf-8")
# Long read timeout and no automatic retries: a first run lost Gordon to a 60 s client timeout,
# while botocore silently retried 4 times and every attempt was generated and billed server-side.
client = boto3.client("bedrock-runtime", region_name=REGION,
                      config=Config(read_timeout=900, retries={"max_attempts": 1, "mode": "standard"}))
raw_dir = HERE / "Risposte modello"
raw_dir.mkdir(exist_ok=True)

log = {"run_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "model_id": MODEL_ID, "region": REGION, "api": "bedrock-runtime Converse",
       "max_tokens": MAX_TOKENS, "calls": []}
total_cost = 0.0
for name in sys.argv[2:] or ["Keith", "Gordon", "Cheney"]:
    img_paths = [IMG_DIR / f"{name}_{part}.jpg" for part in ("oriented", "top", "bottom")]
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [
            *[{"image": {"format": "jpeg", "source": {"bytes": ip.read_bytes()}}} for ip in img_paths],
            {"text": prompt},
        ]}],
        inferenceConfig={"maxTokens": MAX_TOKENS},
        additionalModelRequestFields={"thinking": {"type": "adaptive"}},
    )
    resp.pop("ResponseMetadata", None)
    (raw_dir / f"{name}_response.json").write_text(json.dumps(resp, indent=2, default=str), encoding="utf-8")
    text = "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
    (raw_dir / f"{name}_answer.txt").write_text(text, encoding="utf-8")
    u = resp["usage"]
    cost = u["inputTokens"] * PRICE_IN / 1e6 + u["outputTokens"] * PRICE_OUT / 1e6
    total_cost += cost
    log["calls"].append({"invoice": name, "images": [ip.name for ip in img_paths], "stop_reason": resp["stopReason"],
                         "usage": u, "estimated_cost_usd": round(cost, 4)})
    print(name, resp["stopReason"], u, f"${cost:.4f}")
log["estimated_total_cost_usd"] = round(total_cost, 4)
(raw_dir / f"run_log_{'_'.join(sys.argv[2:]) or 'all'}.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
print(f"TOTAL ${total_cost:.4f}")
