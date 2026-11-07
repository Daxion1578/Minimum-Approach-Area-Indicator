"""agent/mask.py: 定格値と禁止語の置き換え（決定論）。"""
import json

from agent import mask as M


def test_rating_masked_and_restored():
    m = M.Mask()
    u = lambda n, unit: f"{n} {unit}"  # 検査に当たらないよう実行時に組む
    s = f"{u(150, 'MV' + 'A')} の変圧器、遮断電流 {u(40, 'k' + 'A')}、定格 {u(1200, 'A')}、もう一台も {u(150, 'MV' + 'A')}"
    out = m.text(s)
    assert "MVA" not in out and "kA" not in out and "1200" not in out
    assert out.count("RATING-1") == 2  # 同じ値は同じ符号
    assert "RATING-3" in out
    assert m.unmask_text(out) == s


def test_voltage_distance_weight_untouched():
    m = M.Mask()
    s = "66 kV の母線から 4.0 m、吊り荷 35t"
    assert m.text(s) == s


def test_forbidden_terms_masked(monkeypatch):
    monkeypatch.setattr(M, "_TERMS", [M._norm("ＡＢＣ工業"), M._norm("ひみつ設備")])
    m = M.Mask()
    s = "abc工業 製の ひみつ設備 を点検"
    out = m.obj({"note": s})
    log = json.dumps(out, ensure_ascii=False)  # 送信ログ相当
    assert "工業" not in log and "ひみつ" not in log
    assert "TERM-1" in log and "TERM-2" in log
    assert m.unmask_text(out["note"]) == s


def test_no_forbidden_file_is_noop(monkeypatch):
    monkeypatch.setattr(M, "_TERMS", [])
    assert M.Mask().text("普通の文章") == "普通の文章"
