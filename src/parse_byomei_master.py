"""傷病名マスター（支払基金）をパースしてSQLiteに格納する."""
import csv
import io
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "drug_indication.db"
BYOMEI_FILE = DATA_DIR / "byomei" / "b_20260101.txt"


def parse_byomei_master():
    """傷病名マスターCSVをパースしてレコードリストを返す."""
    with open(BYOMEI_FILE, "rb") as f:
        raw = f.read()
    text = raw.decode("cp932", errors="replace")
    reader = csv.reader(io.StringIO(text))

    records = []
    for row in reader:
        if len(row) < 15 or row[1] != "B":
            continue
        byomei_code = row[2]       # 傷病名コード
        byomei_name = row[5]       # 傷病名（漢字）
        byomei_kana = row[8]       # 傷病名（カナ）
        icd10 = row[15] if len(row) > 15 else ""  # ICD-10
        records.append((byomei_code, byomei_name, byomei_kana, icd10))
    return records


def init_db():
    """SQLiteデータベースを初期化する."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS byomei (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kana TEXT,
            icd10 TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS drug (
            yj_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            generic_name TEXT,
            category TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS indication (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            yj_code TEXT NOT NULL,
            byomei_code TEXT NOT NULL,
            indication_text TEXT,
            source TEXT DEFAULT 'pmda',
            FOREIGN KEY (yj_code) REFERENCES drug(yj_code),
            FOREIGN KEY (byomei_code) REFERENCES byomei(code),
            UNIQUE(yj_code, byomei_code)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_indication_yj ON indication(yj_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_indication_byomei ON indication(byomei_code)")
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS byomei_fts USING fts5(code, name, kana)")
    conn.commit()
    return conn


def load_byomei(conn, records):
    """傷病名マスターをDBにロードする."""
    c = conn.cursor()
    c.executemany(
        "INSERT OR REPLACE INTO byomei (code, name, kana, icd10) VALUES (?, ?, ?, ?)",
        records,
    )
    # FTSを再構築
    c.execute("DELETE FROM byomei_fts")
    c.execute("INSERT INTO byomei_fts(code, name, kana) SELECT code, name, kana FROM byomei")
    conn.commit()


def main():
    print("傷病名マスターをパース中...")
    records = parse_byomei_master()
    print(f"  {len(records)} 件の傷病名を読み込みました")

    print("SQLiteデータベースを初期化中...")
    conn = init_db()
    load_byomei(conn, records)

    # 確認
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM byomei")
    print(f"  DB登録件数: {c.fetchone()[0]}")

    # サンプル検索
    c.execute("SELECT * FROM byomei WHERE name LIKE '%高血圧%' LIMIT 5")
    for row in c.fetchall():
        print(f"  {row}")

    conn.close()
    print("完了")


if __name__ == "__main__":
    main()
