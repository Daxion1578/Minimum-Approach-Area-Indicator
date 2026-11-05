"""重機（移動式クレーン）の包絡（§7.4）。

クレーンを「カプセルの集まり」に落とす。判定はこの包絡と充電導体の包絡の最短距離だけで行う。
諸元は 25t 級ラフテレーンクレーンの例示値（仮定値。公開カタログで確認するまで「要確認」）。

配置の入力（§6.6 crane.json）:
  base: [x, y]            車体中心（m、構内ローカル）
  heading_deg: 0          車体の向き（x 軸から反時計回り。0 なら車体は x 方向に長い）
  boom_len_m: 20          ブーム長（伸ばした長さ）
  boom_elev_deg: 60       ブームの起伏角（水平から）
  slew_deg: [-30, 40]     旋回範囲（車体の向きを 0 として、反時計回りが正）
  boom_elev2_deg: 70      任意。2 つ目の起伏角（吊る点と置く点で作業半径が違うとき）。両方で掃引する
  hook_drop_m: 3          ブーム先端からフックまでの垂下
  load: {"w": 2.0, "d": 2.0, "h": 2.5}   吊荷（箱）
  class: "25t"            任意。data/tables/cranes.json のクラス（車体寸法・ブーム根元の高さ）。無ければ例示の 25t 級
掃引: 旋回範囲を step_deg ごとに刻み、各角度でブーム・フックロープ・吊荷のカプセルを作る。
刻みの間の動きを見落とさないように、ブーム・ロープ・吊荷の半径に「先端までの水平距離 × sin(刻み/2)」を足す（保守側）。
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
    boom_elev2_deg: float | None = None
    crane_class: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Crane":
        spec = dict(DEFAULT_SPEC)
        if d.get("class"):
            from engine.crane_select import load_classes
            k = next((c for c in load_classes() if c["id"] == d["class"]), None)
            if k:
                spec = spec_of(k)
        return cls(
            spec=spec, crane_class=d.get("class"),
            boom_elev2_deg=float(d["boom_elev2_deg"]) if d.get("boom_elev2_deg") is not None else None,
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
                "load": self.load, "spec": self.spec["model"],
                **({"boom_elev2_deg": self.boom_elev2_deg} if self.boom_elev2_deg is not None else {}),
                **({"class": self.crane_class} if self.crane_class else {})}

    # ---- 幾何 ----
    def pivot(self) -> tuple[float, float, float]:
        h = math.radians(self.heading_deg)
        px = self.base[0] + self.spec["pivot"]["x_rear"] * math.cos(h)
        py = self.base[1] + self.spec["pivot"]["x_rear"] * math.sin(h)
        return (px, py, self.spec["pivot"]["z"])

    def tip(self, slew_deg: float, elev_deg: float | None = None) -> tuple[float, float, float]:
        px, py, pz = self.pivot()
        az = math.radians(self.heading_deg + slew_deg)
        el = math.radians(self.boom_elev_deg if elev_deg is None else elev_deg)
        horiz = self.boom_len_m * math.cos(el)
        return (px + horiz * math.cos(az), py + horiz * math.sin(az), pz + self.boom_len_m * math.sin(el))

    def capsules_at(self, slew_deg: float, elev_deg: float | None = None, pad: float = 0.0) -> list[dict]:
        """ある旋回角での包絡カプセル（ブーム・ロープ・吊荷）。pad は刻みの間の動きを含めるための半径の上乗せ。"""
        p = self.pivot(); t = self.tip(slew_deg, elev_deg)
        hook = (t[0], t[1], max(t[2] - self.hook_drop_m, 0.5))
        lw, ld, lh = self.load["w"], self.load["d"], self.load["h"]
        load_r = max(lw, ld) / 2 + self.spec["load_r_extra"]
        load_top = hook
        load_bot = (hook[0], hook[1], max(hook[2] - lh, 0.0))
        return [
            {"part": "boom", "a": list(p), "b": list(t), "r": round(self.spec["boom_r"] + pad, 3), "slew_deg": slew_deg},
            {"part": "rope", "a": list(t), "b": list(hook), "r": round(self.spec["rope_r"] + pad, 3), "slew_deg": slew_deg},
            {"part": "load", "a": list(load_top), "b": list(load_bot), "r": round(load_r + pad, 3), "slew_deg": slew_deg},
        ]

    def carrier_capsules(self) -> list[dict]:
        h = math.radians(self.heading_deg)
        L, W, H = self.spec["carrier"]["len"], self.spec["carrier"]["w"], self.spec["carrier"]["h"]
        dx, dy = math.cos(h) * (L / 2 - W / 2), math.sin(h) * (L / 2 - W / 2)
        a = (self.base[0] - dx, self.base[1] - dy, H / 2)
        b = (self.base[0] + dx, self.base[1] + dy, H / 2)
        return [{"part": "carrier", "a": list(a), "b": list(b), "r": W / 2, "slew_deg": None}]

    def reach(self, elev_deg: float | None = None) -> float:
        """ブームの根元から先端までの水平距離（作業半径の目安）。"""
        return self.boom_len_m * math.cos(math.radians(self.boom_elev_deg if elev_deg is None else elev_deg))

    def sweep(self, step_deg: float = 2.0) -> list[dict]:
        lo, hi = self.slew_deg
        n = max(1, int(math.ceil((hi - lo) / step_deg)))
        angles = [lo + (hi - lo) * i / n for i in range(n + 1)]
        d = (hi - lo) / n if hi > lo else 0.0
        caps = self.carrier_capsules()
        elevs = [self.boom_elev_deg] + ([self.boom_elev2_deg] if self.boom_elev2_deg is not None else [])
        for el in elevs:
            # 隣り合う角度の間の点は、どちらかの角度の点から「水平距離 × sin(刻み/2)」以内にある（刻みの間を見落とさない）
            pad = (self.reach(el) + max(self.load["w"], self.load["d"])) * math.sin(math.radians(d / 2.0))
            for a in angles:
                caps.extend(self.capsules_at(a, el, pad))
        return caps


def spec_of(k: dict) -> dict:
    """data/tables/cranes.json のクラス → 幾何の諸元。"""
    return {"model": k["name"], "carrier": dict(k["carrier"]), "pivot": dict(k["pivot"]),
            "boom_r": k.get("boom_r", DEFAULT_SPEC["boom_r"]), "rope_r": DEFAULT_SPEC["rope_r"],
            "load_r_extra": DEFAULT_SPEC["load_r_extra"]}
