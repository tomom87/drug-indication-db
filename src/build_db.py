"""シードデータを傷病名マスターと突合してSQLiteに格納する."""
import sqlite3
from pathlib import Path

from indication_seed import get_indication_map
from indication_seed_ext import get_indication_map_ext
from indication_seed_dosage import get_indication_map_dosage
from drug_seed import NAIKA_DRUGS, TSUMURA_KAMPO
from drug_seed_ext import NAIKA_DRUGS_EXT
from drug_seed_dosage import NAIKA_DRUGS_DOSAGE, DOSAGE_REPLACES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "drug_indication.db"


def find_byomei_code(cursor, name: str) -> str | None:
    """傷病名マスターから病名コードを検索する.

    完全一致 → 部分一致の順で検索。
    """
    # 完全一致
    cursor.execute("SELECT code FROM byomei WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    # 全角・半角の揺れを考慮して部分一致
    cursor.execute("SELECT code, name FROM byomei WHERE name LIKE ?", (f"%{name}%",))
    rows = cursor.fetchall()
    if rows:
        # 最短一致（最も名前が近いもの）を返す
        best = min(rows, key=lambda r: len(r[1]))
        return best[0]

    return None


def build():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # drugテーブルにデータ投入
    drug_id = 0
    drug_keys = {}  # drug_key -> yj_code (ここでは連番IDで代用)

    # DOSAGE_REPLACESに含まれる薬剤は除外し、用量別エントリに置き換え
    base_drugs = [
        (name, cat) for name, cat in NAIKA_DRUGS + NAIKA_DRUGS_EXT
        if name not in DOSAGE_REPLACES
    ]
    all_naika = base_drugs + NAIKA_DRUGS_DOSAGE

    for name, category in all_naika:
        drug_id += 1
        yj_code = f"NAIKA_{drug_id:04d}"
        c.execute(
            "INSERT OR REPLACE INTO drug (yj_code, name, generic_name, category) VALUES (?, ?, ?, ?)",
            (yj_code, name, name, category),
        )
        drug_keys[name] = yj_code

    for num, name, kana in TSUMURA_KAMPO:
        yj_code = f"TJ_{num:03d}"
        full_name = f"ツムラ{name}エキス顆粒（医療用）"
        c.execute(
            "INSERT OR REPLACE INTO drug (yj_code, name, generic_name, category) VALUES (?, ?, ?, ?)",
            (yj_code, full_name, name, "漢方"),
        )
        drug_keys[full_name] = yj_code

    conn.commit()

    # indicationテーブルにデータ投入
    indication_map = get_indication_map()
    indication_map.update(get_indication_map_ext())
    # 用量別データで上書き（単一エントリの適応は用量別に分割される）
    dosage_map = get_indication_map_dosage()
    # DOSAGE_REPLACESの元エントリを削除
    for name in DOSAGE_REPLACES:
        indication_map.pop(name, None)
    indication_map.update(dosage_map)
    matched = 0
    unmatched_names = set()

    for drug_key, data in indication_map.items():
        yj_code = drug_keys.get(drug_key)
        if not yj_code:
            continue

        for byomei_name in data["byomei_names"]:
            byomei_code = find_byomei_code(c, byomei_name)
            if byomei_code:
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO indication (yj_code, byomei_code, indication_text, source) VALUES (?, ?, ?, ?)",
                        (yj_code, byomei_code, data["indication_text"], "pmda_seed"),
                    )
                    matched += 1
                except sqlite3.IntegrityError:
                    pass
            else:
                unmatched_names.add(byomei_name)

    conn.commit()

    # 統計
    c.execute("SELECT COUNT(*) FROM drug")
    drug_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM indication")
    indication_count = c.fetchone()[0]

    print(f"薬剤数: {drug_count}")
    print(f"マッピング成功: {matched}")
    print(f"DB登録済みindication: {indication_count}")
    print(f"未マッチ病名数: {len(unmatched_names)}")
    if unmatched_names:
        print("未マッチ病名:")
        for name in sorted(unmatched_names):
            print(f"  - {name}")

    # サンプルクエリ: アムロジピンの適応病名
    print("\n--- サンプル: アムロジピンの適応病名 ---")
    c.execute("""
        SELECT d.name, b.name, b.icd10
        FROM indication i
        JOIN drug d ON i.yj_code = d.yj_code
        JOIN byomei b ON i.byomei_code = b.code
        WHERE d.generic_name = 'アムロジピン'
    """)
    for row in c.fetchall():
        print(f"  {row[0]} → {row[1]} (ICD-10: {row[2]})")

    # サンプル: 葛根湯
    print("\n--- サンプル: ツムラ葛根湯の適応病名 ---")
    c.execute("""
        SELECT d.name, b.name, b.icd10
        FROM indication i
        JOIN drug d ON i.yj_code = d.yj_code
        JOIN byomei b ON i.byomei_code = b.code
        WHERE d.generic_name = '葛根湯'
    """)
    for row in c.fetchall():
        print(f"  {row[0]} → {row[1]} (ICD-10: {row[2]})")

    # サンプル: 逆引き - 高血圧症に使える薬
    print("\n--- サンプル: 高血圧症に適応のある薬剤 ---")
    c.execute("""
        SELECT d.name, d.category
        FROM indication i
        JOIN drug d ON i.yj_code = d.yj_code
        JOIN byomei b ON i.byomei_code = b.code
        WHERE b.name = '高血圧症'
        ORDER BY d.category, d.name
    """)
    for row in c.fetchall():
        print(f"  [{row[1]}] {row[0]}")

    conn.close()


if __name__ == "__main__":
    build()
