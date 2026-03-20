"""SQLiteデータベースからGitHub Pages用の静的JSONファイルを生成する."""
import json
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "drug_indication.db"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
API_DIR = DOCS_DIR / "api"


def export():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 出力ディレクトリ作成
    API_DIR.mkdir(parents=True, exist_ok=True)
    (API_DIR / "drugs").mkdir(exist_ok=True)
    (API_DIR / "byomei").mkdir(exist_ok=True)

    # --- 1. 薬剤一覧 ---
    c.execute("SELECT yj_code, name, generic_name, category FROM drug ORDER BY category, name")
    drugs = [dict(row) for row in c.fetchall()]
    write_json(API_DIR / "drugs.json", drugs)

    # --- 2. 各薬剤の適応病名 ---
    for drug in drugs:
        yj = drug["yj_code"]
        c.execute("""
            SELECT b.code, b.name, b.kana, b.icd10
            FROM indication i
            JOIN byomei b ON i.byomei_code = b.code
            WHERE i.yj_code = ?
            ORDER BY b.name
        """, (yj,))
        indications = [dict(row) for row in c.fetchall()]
        write_json(API_DIR / "drugs" / f"{yj}.json", {
            "drug": drug,
            "indications": indications,
        })

    # --- 3. 病名→薬剤の逆引きインデックス ---
    c.execute("""
        SELECT DISTINCT b.code, b.name, b.icd10
        FROM indication i
        JOIN byomei b ON i.byomei_code = b.code
        ORDER BY b.name
    """)
    byomei_list = [dict(row) for row in c.fetchall()]
    write_json(API_DIR / "byomei.json", byomei_list)

    for byo in byomei_list:
        code = byo["code"]
        c.execute("""
            SELECT d.yj_code, d.name, d.generic_name, d.category
            FROM indication i
            JOIN drug d ON i.yj_code = d.yj_code
            WHERE i.byomei_code = ?
            ORDER BY d.category, d.name
        """, (code,))
        drug_list = [dict(row) for row in c.fetchall()]
        write_json(API_DIR / "byomei" / f"{code}.json", {
            "byomei": byo,
            "drugs": drug_list,
        })

    # --- 4. 全マッピングのフラットテーブル（検索用） ---
    c.execute("""
        SELECT d.yj_code, d.name as drug_name, d.generic_name, d.category,
               b.code as byomei_code, b.name as byomei_name, b.icd10
        FROM indication i
        JOIN drug d ON i.yj_code = d.yj_code
        JOIN byomei b ON i.byomei_code = b.code
        ORDER BY d.name, b.name
    """)
    all_mappings = [dict(row) for row in c.fetchall()]
    write_json(API_DIR / "mappings.json", all_mappings)

    # --- 5. 統計 ---
    c.execute("SELECT COUNT(*) FROM drug")
    drug_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM indication")
    indication_count = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT yj_code) FROM indication")
    mapped_drug_count = c.fetchone()[0]
    c.execute("SELECT category, COUNT(*) as count FROM drug GROUP BY category ORDER BY count DESC")
    categories = [dict(row) for row in c.fetchall()]

    write_json(API_DIR / "stats.json", {
        "drug_count": drug_count,
        "indication_count": indication_count,
        "mapped_drug_count": mapped_drug_count,
        "byomei_with_drugs": len(byomei_list),
        "categories": categories,
    })

    conn.close()

    print(f"エクスポート完了:")
    print(f"  薬剤数: {drug_count}")
    print(f"  マッピング数: {indication_count}")
    print(f"  適応病名数: {len(byomei_list)}")
    print(f"  出力先: {API_DIR}")


def write_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    export()
