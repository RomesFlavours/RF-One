"""Explicit live smoke test: generated synthetic CV only; never reads existing CVs.
Run: python -X utf8 test_sp_openai_live.py
No key or raw API response is written. At most 2 text calls and 2 OCR attempts.
"""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import date
sys.path[:0] = [str(Path(__file__).parent), str(Path(__file__).parent.parent / "RF-One Data Store")]
from workspace.sp import provider, analysis, profiles
from workspace import ai_adapter, cv_reading

CV = """Synthetic Alex Example
synthetic.alex@example.test
(407) 555-0132
Experience
Server, Synthetic Trattoria | Jan 2019 - Dec 2021
Provided full table service and wine recommendations to 40 guests nightly.
Server, Synthetic Bistro | Jan 2022 - Present
Managed six tables per shift, operated Toast POS and trained new servers.
Skills
Wine service, POS, upselling
"""

def main():
    if not provider._api_key():
        print("BLOCKED: OpenAI secret absent. No API request made; cost USD 0.")
        return 2
    os.environ.update(RFONE_SP_SYNTHETIC_ONLY="1", RFONE_SP_AI_PROVIDER="OPENAI", RFONE_SP_AI_FALLBACK="")
    ai_adapter.bind_policy(ai_adapter.AIPolicy(ai_enabled=True, cv_ai_authorized=True))
    receipts = []
    original = provider._post
    def tracked(payload, timeout):
        result = original(payload, timeout)
        usage = result.get("usage", {})
        inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        cached = usage.get("input_tokens_details", {}).get("cached_tokens", 0)
        receipts.append({"input_tokens": inp, "cached_tokens": cached, "output_tokens": out,
                         "estimated_usd": ((inp-cached) + cached * .05 + out * 5)/1_000_000})
        return result
    provider._post = tracked
    try:
        requirements = profiles.default_requirements("SERVER")
        result = analysis.analyze_cv(role_code="SERVER", requirements=requirements, cv_text=CV, today=date(2026,11,3))
        assert len(result["jobs"]) == 2, "work history incomplete"
        assert "2019" in analysis.build_prompt("SERVER", requirements, CV)
        from PIL import Image, ImageDraw, ImageFont
        with tempfile.TemporaryDirectory(prefix="sp_synthetic_scan_") as temp:
            image = Image.new("RGB", (1400, 1100), "white")
            font = ImageFont.truetype("arial.ttf", 25)
            ImageDraw.Draw(image).multiline_text((35,35), CV, font=font, fill="black", spacing=12)
            path = str(Path(temp) / "synthetic-scan.pdf")
            image.save(path, "PDF")
            transcribed = cv_reading.transcribe_pdf(path, sp=True)
            assert "Synthetic Alex" in transcribed and "2019" in transcribed
        print("PASS: real OpenAI text analysis and raster-PDF OCR on generated synthetic CV.")
        return 0
    finally:
        provider._post = original
        receipt = {"synthetic_only": True, "model": provider.MODEL, "successful_request_usage": receipts,
                   "estimated_total_usd": sum(r["estimated_usd"] for r in receipts),
                   "note": "Token-based estimate; interrupted or rejected requests may require billing reconciliation."}
        Path("openai-live-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps(receipt, indent=2))

if __name__ == "__main__":
    sys.exit(main())
