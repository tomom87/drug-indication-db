"""医薬品マスターから販売名を抽出し、一般名（generic_name）と紐づける."""
import csv
import io
import re
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "drug_indication.db"
IYAKUHIN_FILE = DATA_DIR / "iyakuhin" / "y_20260317.csv"


def parse_iyakuhin_master() -> list[dict]:
    with open(IYAKUHIN_FILE, "rb") as f:
        raw = f.read()
    text = raw.decode("cp932", errors="replace")
    reader = csv.reader(io.StringIO(text))
    records = []
    for row in reader:
        if len(row) < 35 or row[1] != "Y":
            continue
        yj_code = row[31] if len(row) > 31 else ""
        if not yj_code or len(yj_code) < 7:
            continue
        records.append({
            "name": row[4],
            "kana": row[6],
            "yj_code": yj_code,
            "yj7": yj_code[:7],
            "yj9": yj_code[:9] if len(yj_code) >= 9 else yj_code[:7],
        })
    return records


def strip_dosage_info(name: str) -> str:
    """用量付き薬剤名から基本一般名を抽出."""
    base = re.sub(r'[\d０-９]+\.?[\d０-９]*\s*(mg|ｍｇ|%|％).*$', '', name)
    base = re.sub(r'(経口|注射|持続性注射|低用量|高用量).*$', '', base)
    return base.rstrip('（(').strip()


def build_brand_mapping():
    from drug_seed_dosage import DOSAGE_BRAND_RULES, DOSAGE_REPLACES

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # キュレーション済み薬剤を取得
    c.execute("SELECT yj_code, name, generic_name FROM drug WHERE yj_code LIKE 'NAIKA_%' OR yj_code LIKE 'TJ_%'")
    curated_drugs = [dict(row) for row in c.fetchall()]
    print(f"キュレーション済み薬剤: {len(curated_drugs)} 件")

    iyakuhin = parse_iyakuhin_master()
    print(f"医薬品マスター: {len(iyakuhin)} 件")

    # 用量別薬剤の基本名（先発品名含む）→全YJ7を収集
    dosage_base_yj7s = set()
    dosage_all_base_names = set(DOSAGE_REPLACES)
    for base_names, _ in DOSAGE_BRAND_RULES:
        dosage_all_base_names.update(base_names)
    for base_name in dosage_all_base_names:
        for item in iyakuhin:
            if base_name in item["name"]:
                dosage_base_yj7s.add(item["yj7"])

    # 用量別薬剤: drug_key -> db_yj_code
    dosage_name_to_yj = {}
    for drug in curated_drugs:
        dosage_name_to_yj[drug["generic_name"]] = drug["yj_code"]

    # 通常薬剤: 基本一般名→YJ7マッピング構築
    yj7_to_drug: dict[str, str] = {}
    for drug in curated_drugs:
        base_gn = strip_dosage_info(drug["generic_name"])
        # 用量別薬剤の基本名はスキップ（キーワードルールで処理）
        if base_gn in DOSAGE_REPLACES:
            continue
        for item in iyakuhin:
            if base_gn in item["name"]:
                yj7_to_drug[item["yj7"]] = drug["yj_code"]

    print(f"YJ7マッピング数: {len(yj7_to_drug)}")

    # テーブル作成
    c.execute("DROP TABLE IF EXISTS brand_name")
    c.execute("""
        CREATE TABLE brand_name (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            yj_code TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            brand_kana TEXT,
            master_yj7 TEXT,
            master_yj9 TEXT,
            FOREIGN KEY (yj_code) REFERENCES drug(yj_code)
        )
    """)

    # 全医薬品マスター品目を紐づけてDB保存
    inserted = 0
    for item in iyakuhin:
        assigned_yj = None

        # 用量別薬剤: 基本名リストで絞り込み→キーワードで振り分け
        if item["yj7"] in dosage_base_yj7s:
            for base_names, rules in DOSAGE_BRAND_RULES:
                if not any(bn in item["name"] for bn in base_names):
                    continue
                for drug_key, keywords in rules:
                    if any(kw in item["name"] for kw in keywords):
                        assigned_yj = dosage_name_to_yj.get(drug_key)
                        break
                break

        # 通常のYJ7マッチ
        if not assigned_yj:
            assigned_yj = yj7_to_drug.get(item["yj7"])

        if assigned_yj:
            c.execute(
                "INSERT INTO brand_name (yj_code, brand_name, brand_kana, master_yj7, master_yj9) VALUES (?, ?, ?, ?, ?)",
                (assigned_yj, item["name"], item["kana"], item["yj7"], item["yj9"]),
            )
            inserted += 1

    conn.commit()
    c.execute("CREATE INDEX IF NOT EXISTS idx_brand_yj ON brand_name(yj_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_brand_master_yj7 ON brand_name(master_yj7)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_brand_master_yj9 ON brand_name(master_yj9)")

    c.execute("SELECT COUNT(*) FROM brand_name")
    print(f"DB登録販売名: {c.fetchone()[0]} 件")
    conn.close()


if __name__ == "__main__":
    build_brand_mapping()
