"""外に出す前の置き換え（置換表方式）。決定論で動き、モデルを呼ばない。

社内情報を外部 API に渡せない現場で使える前提条件。送るのは次だけ:
  - 機器種別・開閉器番号の「形」（英数字と記号）・電圧階級・接続関係・座標（構内ローカル、m）
  - 線路名・変電所名・地名は符号に置き換える（LINE-1, SITE）。置換表はローカルに残し、戻すのもローカル
  - 定格値（容量・遮断電流・定格電流。容量・遮断電流・定格電流の数値＋単位）は RATING-n に置き換える。電圧（kV）・距離（m）・重さ（t）は計算に要るので残す
  - 手元の禁止語リスト（.forbidden-terms.local.txt）にある語は TERM-n に置き換える。語そのものは置換表（ローカル）にだけ残り、送信ログには符号だけが残る
数値（容量・整定・潮流）は最初から持たない（§12）。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

FORBIDDEN_FILE = Path(__file__).resolve().parent.parent / ".forbidden-terms.local.txt"
_TERMS: list[str] | None = None  # 読み込みは 1 回だけ（正規化済み）


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold()


def forbidden_terms() -> list[str]:
    global _TERMS
    if _TERMS is None:
        _TERMS = []
        if FORBIDDEN_FILE.exists():
            for line in FORBIDDEN_FILE.read_text(encoding="utf-8").splitlines():
                t = line.strip()
                if t and not t.startswith("#"):
                    _TERMS.append(_norm(t))
        _TERMS.sort(key=len, reverse=True)
    return _TERMS


_RATING = re.compile(r"(\d+(?:\.\d+)?)\s*(MVA|kVA|MW|Mvar|MVar|kA|A)\b")

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

    def _terms(self, s: str) -> str:
        terms = forbidden_terms()
        if not terms or not s:
            return s
        norm, idx = [], []  # 正規化後の各文字が元の何文字目に当たるか
        for i, ch in enumerate(s):
            for c in _norm(ch):
                norm.append(c)
                idx.append(i)
        norm = "".join(norm)
        spans = []
        for t in terms:
            for m in re.finditer(re.escape(t), norm):
                a, b = idx[m.start()], idx[m.end() - 1] + 1
                if not any(a < y and x < b for x, y in spans):
                    spans.append((a, b))
        for a, b in sorted(spans, reverse=True):
            s = s[:a] + self.code_for(s[a:b], "TERM") + s[b:]
        return s

    def text(self, s: str) -> str:
        """文章中の禁止語・定格値・線路名・所名を符号に。"""
        s = self._terms(s)
        s = _RATING.sub(lambda m: self.code_for(m.group(0), "RATING"), s)
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
