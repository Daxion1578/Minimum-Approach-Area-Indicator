"""Claude API を呼ぶ唯一の場所。必ず agent/mask.py を通し、送った内容を logs/outbound/ に残す。

設定は .env（MAAI_ANTHROPIC_API_KEY, MAAI_MODEL_STRUCTURE, MAAI_MODEL_PROPOSE, MAAI_OFFLINE）。
キーが無い／MAAI_OFFLINE=1 のときは呼ばず、呼び出し側の決定論の代替に任せる（available() が False）。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from agent.mask import Mask

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
LOG_DIR = ROOT / "logs" / "outbound"

DEFAULT_MODELS = {"structure": "claude-sonnet-4-5", "propose": "claude-sonnet-4-5"}


def available() -> bool:
    return bool(os.environ.get("MAAI_ANTHROPIC_API_KEY")) and os.environ.get("MAAI_OFFLINE", "0") != "1"


def model_for(purpose: str) -> str:
    return os.environ.get(f"MAAI_MODEL_{purpose.upper()}") or DEFAULT_MODELS[purpose]


def ask_json(purpose: str, system: str, user_obj: dict, mask: Mask | None = None, max_tokens: int = 4000) -> dict | None:
    """マスクした JSON を渡し、JSON を受け取る。呼べないときは None。"""
    if not available():
        return None
    mask = mask or Mask()
    masked = mask.obj(user_obj)
    body = json.dumps(masked, ensure_ascii=False)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{int(time.time())}-{purpose}"
    (LOG_DIR / f"{stamp}.request.json").write_text(json.dumps({"model": model_for(purpose), "system": system, "user": masked}, ensure_ascii=False, indent=1), encoding="utf-8")
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["MAAI_ANTHROPIC_API_KEY"])
    msg = client.messages.create(model=model_for(purpose), max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": body + "\n\nJSON だけを返してください。"}])
    text = "".join(getattr(b, "text", "") for b in msg.content)
    (LOG_DIR / f"{stamp}.response.txt").write_text(text, encoding="utf-8")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.startswith("json") else text
    try:
        return json.loads(mask.unmask_text(text))
    except json.JSONDecodeError:
        return None
