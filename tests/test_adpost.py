# v17: 애드포스트 리포트 CSV 파싱·점수 환산 (고도화 1)
import pytest

from adpost import adpost_performance_score, parse_adpost_csv


def test_parse_utf8_bom_csv():
    raw = ("게시물 제목,URL,수익(원),노출수,클릭수\n"
           "에어프라이어 추천,https://blog.naver.com/a/1,\"1,500\",3000,20\n"
           ).encode("utf-8-sig")
    rows = parse_adpost_csv(raw)
    assert len(rows) == 1
    assert rows[0]["title"] == "에어프라이어 추천"
    assert rows[0]["url"] == "https://blog.naver.com/a/1"
    assert rows[0]["revenue"] == 1500.0  # 콤마 제거
    assert rows[0]["impressions"] == 3000.0
    assert rows[0]["clicks"] == 20.0


def test_parse_cp949_csv():
    raw = ("게시물 제목,수익\n보험 비교 방법,300원\n").encode("cp949")
    rows = parse_adpost_csv(raw)
    assert rows[0]["title"] == "보험 비교 방법"
    assert rows[0]["revenue"] == 300.0


def test_missing_columns_raise():
    with pytest.raises(ValueError):
        parse_adpost_csv("날짜,조회\n".encode("utf-8"))  # 제목/URL 없음
    with pytest.raises(ValueError):
        parse_adpost_csv("게시물 제목,노출수\n".encode("utf-8"))  # 수익 없음
    with pytest.raises(ValueError):
        parse_adpost_csv(b"")  # 빈 파일


def test_empty_rows_skipped():
    raw = "게시물 제목,수익\n\n제목1,100\n,,\n".encode("utf-8-sig")
    rows = parse_adpost_csv(raw)
    assert len(rows) == 1


def test_performance_score_weights():
    # 수익 60 + 노출 25 + 클릭 15 — 만점 기준 클램프
    assert adpost_performance_score(3000, 5000, 100) == 100.0
    assert adpost_performance_score(30000, 50000, 1000) == 100.0  # 상한 클램프
    assert adpost_performance_score(0, 0, 0) == 0.0
    assert adpost_performance_score(1500, 2500, 50) == 60.0 * 0.5 + 25.0 * 0.5 + 15.0 * 0.5
    # 음수 방어
    assert adpost_performance_score(-100, -5, -1) == 0.0
