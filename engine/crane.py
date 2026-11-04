"""重機（移動式クレーン）の包絡（§7.4）。

クレーンを「カプセルの集まり」に落とす。判定はこの包絡と充電導体の包絡の最短距離だけで行う。
諸元は 25t 級ラフテレーンクレーンの例示値（仮定値。公開カタログで確認するまで「要確認」）。

配置の入力（§6.6 crane.json）:
  base: [x, y]            車体中心（m、構内ローカル）
  heading_deg: 0          車体の向き（x 軸から反時計回り。0 なら車体は x 方向に長い）
  boom_len_m: 20          ブーム長（伸ばした長さ）
  boom_elev_deg: 60       ブームの起伏角（水平から）
  slew_deg: [-30, 40]     旋回範囲（車体の向きを 0 として、反時計回りが正）
  hook_drop_m: 3          ブーム先端からフックまでの垂下
  load: {"w": 2.0, "d": 2.0, "h": 2.5}   吊荷（箱）
掃引: 旋回範囲を step_deg ごとに刻み、各角度でブーム・フックロープ・吊荷のカプセルを作る。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

DEFAULT_SPEC = {
    "model": "RT-25（例示値）",
    "carrier": {"len": 7.0, "w": 2.8, "h": 1.6},        # 車体
    "pivot": {"x_rear": -1.0, "z": 2.6},               # ブームの根元（車体中心からの後方オフセット、高さ）
    "boom_r": 0.45,                                     # ブーム断面を包むカプセル半径
    "rope_r": 0.15,
    "load_r_extra": 0.2,
}


@dataclass
class Crane:
    base: tuple[float, float]
    heading_deg: float = 0.0
    boom_len_m: float = 20.0
    boom_elev_deg: float = 60.0
    slew_deg: tuple[float, float] = (-30.0, 40.0)
    hook_drop_m: float = 3.0
    load: dict = field(default_factory=lambda: {"w": 2.0, "d": 2.0, "h": 2.5})
    spec: dict = field(default_factory=lambda: dict(DEFAULT_SPEC))

    @classmethod
    def from_dict(cls, d: dict) -> "Crane":
        return cls(
            base=(float(d["base"][0]), float(d["base"][1])),
            heading_deg=float(d.get("heading_deg", 0.0)),
            boom_len_m=float(d.get("boom_len_m", 20.0)),
            boom_elev_deg=float(d.get("boom_elev_deg", 60.0)),
            slew_deg=(float(d.get("slew_deg", [-30, 40])[0]), float(d.get("slew_deg", [-30, 40])[1])),
            hook_drop_m=float(d.get("hook_drop_m", 3.0)),
            load=dict(d.get("load", {"w": 2.0, "d": 2.0, "h": 2.5})),
        )

    def to_dict(self) -> dict:
        return {"base": list(self.base), "heading_deg": self.heading_deg, "boom_len_m": self.boom_len_m,
                "boom_elev_deg": self.boom_elev_deg, "slew_deg": list(self.slew_deg), "hook_drop_m": self.hook_drop_m,
                "load": self.load, "spec": self.spec["model"]}

    # ---- 幾何 ----
    def pivot(self) -> tuple[float, float, float]:
        h = math.radians(self.heading_deg)
        px = self.base[0] + self.spec["pivot"]["x_rear"] * math.cos(h)
        py = self.base[1] + self.spec["pivot"]["x_rear"] * math.sin(h)
        return (px, py, self.spec["pivot"]["z"])

    def tip(self, slew_deg: float) -> tuple[float, float, float]:
        px, py, pz = self.pivot()
        az = math.radians(self.heading_deg + slew_deg)
        el = math.radians(self.boom_elev_deg)
        horiz = self.boom_len_m * math.cos(el)
        return (px + horiz * math.cos(az), py + horiz * math.sin(az), pz + self.boom_len_m * math.sin(el))

    def capsules_at(self, slew_deg: float) -> list[dict]:
        """ある旋回角での包絡カプセル（ブーム・ロープ・吊荷）。"""
        p = self.pivot(); t = self.tip(slew_deg)
        hook = (t[0], t[1], max(t[2] - self.hook_drop_m, 0.5))
        lw, ld, lh = self.load["w"], self.load["d"], self.load["h"]
        load_r = max(lw, ld) / 2 + self.spec["load_r_extra"]
        load_top = hook
        load_bot = (hook[0], hook[1], max(hook[2] - lh, 0.0))
        return [
            {"part": "boom", "a": list(p), "b": list(t), "r": self.spec["boom_r"], "slew_deg": slew_deg},
            {"part": "rope", "a": list(t), "b": list(hook), "r": self.spec["rope_r"], "slew_deg": slew_deg},
            {"part": "load", "a": list(load_top), "b": list(load_bot), "r": round(load_r, 3), "slew_deg": slew_deg},
        ]

    def carrier_capsules(self) -> list[dict]:
        h = math.radians(self.heading_deg)
        L, W, H = self.spec["carrier"]["len"], self.spec["carrier"]["w"], self.spec["carrier"]["h"]
        dx, dy = math.cos(h) * (L / 2 - W / 2), math.sin(h) * (L / 2 - W / 2)
        a = (self.base[0] - dx, self.base[1] - dy, H / 2)
        b = (self.base[0] + dx, self.base[1] + dy, H / 2)
        return [{"part": "carrier", "a": list(a), "b": list(b), "r": W / 2, "slew_deg": None}]

    def sweep(self, step_deg: float = 5.0) -> list[dict]:
        lo, hi = self.slew_deg
        n = max(1, int(math.ceil((hi - lo) / step_deg)))
        angles = [lo + (hi - lo) * i / n for i in range(n + 1)]
        caps = self.carrier_capsules()
        for a in angles:
            caps.extend(self.capsules_at(a))
        return caps
