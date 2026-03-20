"""医薬品マスターから販売名を抽出し、一般名（generic_name）と紐づける."""
import csv
import io
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
        })
    return records


def build_brand_mapping():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 手動キュレーション薬剤のみ取得（NAIKA_* と TJ_*）
    c.execute("SELECT yj_code, name, generic_name FROM drug WHERE yj_code LIKE 'NAIKA_%' OR yj_code LIKE 'TJ_%'")
    curated_drugs = [dict(row) for row in c.fetchall()]
    print(f"手動キュレーション薬剤: {len(curated_drugs)} 件")

    # 医薬品マスター全件
    iyakuhin = parse_iyakuhin_master()
    print(f"医薬品マスター: {len(iyakuhin)} 件")

    # Step 1: 一般名→ 医薬品マスターのYJ7桁を収集
    # （一般名が販売名に含まれるものからYJ7桁を取得）
    drug_yj7s: dict[str, set[str]] = {}  # DB yj_code -> set of master YJ7
    for drug in curated_drugs:
        gn = drug["generic_name"]
        yj7_set = set()
        for item in iyakuhin:
            if gn in item["name"]:
                yj7_set.add(item["yj7"])
        if yj7_set:
            drug_yj7s[drug["yj_code"]] = yj7_set

    # Step 2: YJ7桁→DB yj_code の逆引き
    yj7_to_drug: dict[str, str] = {}
    for db_yj, yj7_set in drug_yj7s.items():
        for yj7 in yj7_set:
            yj7_to_drug[yj7] = db_yj

    print(f"YJ7マッピング数: {len(yj7_to_drug)}")

    # Step 3: 全医薬品マスター品目をYJ7桁で紐づけ
    brand_to_drug: dict[str, list[dict]] = {}
    matched_count = 0

    for item in iyakuhin:
        db_yj = yj7_to_drug.get(item["yj7"])
        if db_yj:
            if db_yj not in brand_to_drug:
                brand_to_drug[db_yj] = []
            brand_to_drug[db_yj].append({
                "brand_name": item["name"],
                "brand_kana": item["kana"],
            })
            matched_count += 1

    print(f"販売名マッチ: {matched_count} 件")
    print(f"マッチした薬剤数: {len(brand_to_drug)}")

    # DBに保存
    c.execute("DROP TABLE IF EXISTS brand_name")
    c.execute("""
        CREATE TABLE brand_name (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            yj_code TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            brand_kana TEXT,
            master_yj7 TEXT,
            FOREIGN KEY (yj_code) REFERENCES drug(yj_code)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_brand_yj ON brand_name(yj_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_brand_master_yj7 ON brand_name(master_yj7)")

    # master_yj7も一緒に保存
    for db_yj, yj7_set in drug_yj7s.items():
        brands = brand_to_drug.get(db_yj, [])
        for item in iyakuhin:
            if item["yj7"] in yj7_set:
                c.execute(
                    "INSERT INTO brand_name (yj_code, brand_name, brand_kana, master_yj7) VALUES (?, ?, ?, ?)",
                    (db_yj, item["name"], item["kana"], item["yj7"]),
                )

    conn.commit()
    c.execute("SELECT COUNT(*) FROM brand_name")
    print(f"DB登録販売名: {c.fetchone()[0]} 件")
    conn.close()


if __name__ == "__main__":
    build_brand_mapping()
