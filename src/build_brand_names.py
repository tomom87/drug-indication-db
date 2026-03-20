"""医薬品マスターから販売名を抽出し、一般名（generic_name）と紐づける."""
import csv
import io
import json
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "drug_indication.db"
IYAKUHIN_FILE = DATA_DIR / "iyakuhin" / "y_20260317.csv"


def parse_iyakuhin_master() -> list[dict]:
    """医薬品マスターをパースして販売名リストを返す."""
    with open(IYAKUHIN_FILE, "rb") as f:
        raw = f.read()
    text = raw.decode("cp932", errors="replace")
    reader = csv.reader(io.StringIO(text))

    records = []
    for row in reader:
        if len(row) < 35 or row[1] != "Y":
            continue
        code = row[2]          # 医薬品コード
        name = row[4]          # 販売名
        kana = row[6]          # カナ名
        yj_code = row[31] if len(row) > 31 else ""  # YJコード
        records.append({
            "code": code,
            "name": name,
            "kana": kana,
            "yj_code": yj_code,
        })
    return records


def build_brand_mapping():
    """販売名 → generic_name のマッピングを構築."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # DB内の薬剤一覧を取得
    c.execute("SELECT yj_code, name, generic_name, category FROM drug")
    drugs = {row["yj_code"]: dict(row) for row in c.fetchall()}

    # 一般名リスト（部分一致検索用）
    generic_names = {}
    for d in drugs.values():
        generic_names[d["generic_name"]] = d["yj_code"]

    # 医薬品マスターをパース
    iyakuhin = parse_iyakuhin_master()
    print(f"医薬品マスター: {len(iyakuhin)} 件")

    # 販売名→一般名のマッピング
    brand_to_drug: dict[str, list[dict]] = {}  # yj_code -> [brand_names]
    matched_count = 0

    for item in iyakuhin:
        brand_name = item["name"]
        brand_kana = item["kana"]

        # 一般名との部分一致マッチング
        for generic_name, yj_code in generic_names.items():
            if generic_name in brand_name:
                if yj_code not in brand_to_drug:
                    brand_to_drug[yj_code] = []
                brand_to_drug[yj_code].append({
                    "brand_name": brand_name,
                    "brand_kana": brand_kana,
                })
                matched_count += 1
                break

    print(f"販売名マッチ: {matched_count} 件")
    print(f"マッチした薬剤数: {len(brand_to_drug)}")

    # DBにbrand_namesテーブルを作成
    c.execute("""
        CREATE TABLE IF NOT EXISTS brand_name (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            yj_code TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            brand_kana TEXT,
            FOREIGN KEY (yj_code) REFERENCES drug(yj_code)
        )
    """)
    c.execute("DELETE FROM brand_name")
    c.execute("CREATE INDEX IF NOT EXISTS idx_brand_yj ON brand_name(yj_code)")

    for yj_code, brands in brand_to_drug.items():
        for b in brands:
            c.execute(
                "INSERT INTO brand_name (yj_code, brand_name, brand_kana) VALUES (?, ?, ?)",
                (yj_code, b["brand_name"], b["brand_kana"]),
            )

    conn.commit()

    # 統計
    c.execute("SELECT COUNT(*) FROM brand_name")
    total = c.fetchone()[0]
    print(f"DB登録販売名: {total} 件")

    conn.close()
    return brand_to_drug


if __name__ == "__main__":
    build_brand_mapping()
