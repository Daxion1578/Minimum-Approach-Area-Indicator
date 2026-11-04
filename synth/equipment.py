"""屋外機器の外形寸法ライブラリ（電圧階級ごと。すべて仮定値）。

メーカー公開カタログにある代表的な外形寸法（断路器の碍管高さ・開極スパン・架台幅、遮断器の全高、
変圧器のタンク寸法など）を参考に、合成変電所用に丸めた値。特定の製品・事業者の図面を写したものではない。
図面（synth/gen_drawings.py）と 3D（web/）が同じ値を使うために、ここに一か所で持つ。

単位 m。座標は X=東, Y=北, Z=上。「軸」は電流の流れる向き（ベイの機器列なら y、母線上の機器なら x）。
"""
from __future__ import annotations

# 電圧階級 → 機器種別 → 寸法
EQUIP = {
    220: {   # 245kV 級
        "phase_sp": 4.0,
        "ds": {   # 二点切（水平二点切）断路器: 3 本の碍管、中央が回転して両側で開く
            "column": 2.5,        # 支持架台（鋼）高さ
            "insulator": 2.3,     # 碍管高さ（A）
            "head": 0.35,         # 端子・ブレードの高さ（B-A）
            "span": 2.9,          # 両端碍管の中心間（C）
            "frame": 3.4,         # 架台の長さ（D）
            "frame_w": 0.6, "ins_d": 0.3, "base": 0.8,
        },
        "cb": {   # 碍子形（ライブタンク）遮断器: 碍管の上に水平の遮断部
            "column": 2.6, "post": 2.3, "chamber_len": 2.4, "chamber_d": 0.4, "post_d": 0.35, "base": 1.0,
            "cabinet": (1.0, 1.4, 1.6),   # 操作箱 w, d, h
        },
        "ct": {"column": 1.8, "porcelain": 2.6, "head_d": 0.9, "head_h": 0.8, "post_d": 0.3, "base": 0.9},
        "la": {"column": 1.0, "porcelain": 2.3, "d": 0.25, "base": 0.6},
        "terminal_z": 5.2,        # 機器端子の高さ（column + insulator + head）
    },
    66: {    # 72.5kV 級
        "phase_sp": 1.5,
        "ds": {"column": 2.0, "insulator": 0.8, "head": 0.35, "span": 1.3, "frame": 1.8, "frame_w": 0.4, "ins_d": 0.2, "base": 0.5},
        "cb": {"column": 1.6, "post": 1.2, "chamber_len": 1.2, "chamber_d": 0.28, "post_d": 0.25, "base": 0.6, "cabinet": (0.7, 1.0, 1.2)},
        "ct": {"column": 1.2, "porcelain": 1.4, "head_d": 0.6, "head_h": 0.5, "post_d": 0.22, "base": 0.6},
        "la": {"column": 0.8, "porcelain": 0.9, "d": 0.18, "base": 0.4},
        "terminal_z": 3.2,
    },
}

# 変圧器（220/66kV・三相、タンク中心が原点。HV は北側、LV は南側）
TRANSFORMER = {
    "tank": (8.0, 4.5, 4.5),          # x, y, z
    "radiator_depth": 2.0, "radiator_len": 3.6, "radiator_n": 8,   # 東西両側に放熱器
    "conservator": {"d": 1.4, "len": 6.0, "z": 6.2},               # タンク上、x 方向
    "hv": {"y": 1.6, "top_z": 8.5, "d": 0.4},                      # 一次ブッシング（3 本、x ピッチ 2.2）
    "lv": {"y": -1.6, "top_z": 6.5, "d": 0.3},                     # 二次ブッシング（3 本、x ピッチ 1.6）
    "hv_pitch": 2.2, "lv_pitch": 1.6,
    "bund": (12.0, 8.0),              # 油流出防止堰 x, y
    "found": (9.0, 5.5),              # 基礎
}

# 鉄構（柱は格子鋼、梁は格子）
GANTRY = {"col_w": 1.2, "beam_h": 1.0}

# 調相設備（屋外のラック据付。外形だけ）
LOADS = {
    "SC": {"size": (4.0, 2.5, 3.0), "name": "電力用コンデンサ"},
    "SR": {"size": (3.0, 3.0, 3.5), "name": "分路リアクトル"},
}


def terminal_z(kv: int) -> float:
    return EQUIP[kv]["terminal_z"]
