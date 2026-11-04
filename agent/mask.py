"""外に出す前の置き換え（置換表方式）。決定論で動き、モデルを呼ばない。

社内情報を外部 API に渡せない現場で使える前提条件。送るのは次だけ:
  - 機器種別・開閉器番号の「形」（英数字と記号）・電圧階級・接続関係・座標（構内ローカル、m）
  - 線路名・変電所名・地名は符号に置き換える（LINE-1, SITE）。置換表はローカルに残し、戻すのもローカル
数値（容量・整定・潮流）は最初から持たない（§12）。
"""
from __future__ import annotations

import re

_W = r"[A-Za-z0-9一-龥ァ-ヶー]"
_DIGITS = re.compile(r"[0-9号A-Za-z]")
# 固有名ではない一般語は残す（接続の説明に要る）
GENERIC = {"母線", "線路", "送電線", "配電線", "架空線", "接地線", "結線", "単線", "単線結線図", "導線", "架線", "電線", "線", "曲線", "直線", "市", "町", "駅", "港", "変電所", "開閉所", "発電所"}
GENERIC_SUFFIX = ("母線", "線路", "結線", "送電線", "配電線", "架空線", "接地線", "引込線", "連絡線")
_NAME_WORDS = re.compile(r"[一-龥ァ-ヶー]{0,6}(?:線|変電所|開閉所|発電所|町|市|駅|港)[A-Za-z0-9]{0,4}")


class Mask:
    def __init__(self):
        self.table: dict[str, str] = {}

    def code_for(self, name: str, prefix: str) -> str:
        if name not in self.table:
            self.table[name] = f"{prefix}-{len([v for v in self.table.values() if v.startswith(prefix)]) + 1}"
        return self.table[name]

    def text(self, s: str) -> str:
        """文章中の線路名・所名を符号に。"""
        def rep(m):
            w = m.group(0)
            core = _DIGITS.sub("", w)
            if not w or w.isdigit() or core in GENERIC or any(core.endswith(g) for g in GENERIC_SUFFIX):
                return w
            prefix = "SITE" if ("変電所" in w or "開閉所" in w or "発電所" in w) else "LINE" if "線" in w else "PLACE"
            return self.code_for(w, prefix)
        return _NAME_WORDS.sub(rep, s)

    def obj(self, o):
        """JSON（dict/list/str）を再帰的に置き換える。"""
        if isinstance(o, str):
            return self.text(o)
        if isinstance(o, list):
            return [self.obj(v) for v in o]
        if isinstance(o, dict):
            return {k: self.obj(v) for k, v in o.items()}
        return o

    def unmask_text(self, s: str) -> str:
        for name, code in sorted(self.table.items(), key=lambda kv: -len(kv[1])):
            s = s.replace(code, name)
        return s
