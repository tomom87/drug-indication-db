"""薬剤-適応病名マッピングAPI.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8100 --reload
"""
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "drug_indication.db"

app = FastAPI(
    title="薬剤-適応病名マッピングAPI",
    description="内科頻用薬95品目＋ツムラ漢方128処方の保険適応病名データベース",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/drugs", summary="薬剤一覧")
def list_drugs(
    q: str = Query(None, description="薬剤名で検索（部分一致）"),
    category: str = Query(None, description="カテゴリで絞り込み"),
):
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT yj_code, name, generic_name, category FROM drug WHERE 1=1"
    params = []
    if q:
        sql += " AND (name LIKE ? OR generic_name LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY category, name"
    c.execute(sql, params)
    drugs = [dict(row) for row in c.fetchall()]
    conn.close()
    return drugs


@app.get("/drugs/{yj_code}/indications", summary="薬剤の適応病名一覧")
def drug_indications(yj_code: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT b.code, b.name, b.kana, b.icd10, i.indication_text
        FROM indication i
        JOIN byomei b ON i.byomei_code = b.code
        WHERE i.yj_code = ?
        ORDER BY b.name
    """, (yj_code,))
    indications = [dict(row) for row in c.fetchall()]

    c.execute("SELECT name, generic_name, category FROM drug WHERE yj_code = ?", (yj_code,))
    drug = c.fetchone()
    conn.close()

    if not drug:
        return JSONResponse(status_code=404, content={"error": "薬剤が見つかりません"})

    return {
        "drug": dict(drug),
        "indications": indications,
    }


@app.get("/byomei/search", summary="病名検索")
def search_byomei(
    q: str = Query(..., description="病名キーワード（部分一致）"),
):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT code, name, kana, icd10 FROM byomei WHERE name LIKE ? ORDER BY name LIMIT 50",
        (f"%{q}%",),
    )
    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results


@app.get("/byomei/{byomei_code}/drugs", summary="病名→適応薬剤の逆引き")
def byomei_drugs(byomei_code: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT d.yj_code, d.name, d.generic_name, d.category, i.indication_text
        FROM indication i
        JOIN drug d ON i.yj_code = d.yj_code
        WHERE i.byomei_code = ?
        ORDER BY d.category, d.name
    """, (byomei_code,))
    drugs = [dict(row) for row in c.fetchall()]

    c.execute("SELECT code, name, kana, icd10 FROM byomei WHERE code = ?", (byomei_code,))
    byomei = c.fetchone()
    conn.close()

    if not byomei:
        return JSONResponse(status_code=404, content={"error": "病名が見つかりません"})

    return {
        "byomei": dict(byomei),
        "drugs": drugs,
    }


@app.get("/lookup", summary="薬剤名または病名から横断検索")
def lookup(
    drug: str = Query(None, description="薬剤名（部分一致）"),
    byomei: str = Query(None, description="病名（部分一致）"),
):
    if not drug and not byomei:
        return JSONResponse(
            status_code=400,
            content={"error": "drugまたはbyomeiパラメータが必要です"},
        )

    conn = get_db()
    c = conn.cursor()

    if drug:
        c.execute("""
            SELECT d.name as drug_name, d.category, b.name as byomei_name, b.icd10
            FROM indication i
            JOIN drug d ON i.yj_code = d.yj_code
            JOIN byomei b ON i.byomei_code = b.code
            WHERE d.name LIKE ? OR d.generic_name LIKE ?
            ORDER BY d.name, b.name
        """, (f"%{drug}%", f"%{drug}%"))
    else:
        c.execute("""
            SELECT d.name as drug_name, d.category, b.name as byomei_name, b.icd10
            FROM indication i
            JOIN drug d ON i.yj_code = d.yj_code
            JOIN byomei b ON i.byomei_code = b.code
            WHERE b.name LIKE ?
            ORDER BY d.category, d.name
        """, (f"%{byomei}%",))

    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results


@app.get("/stats", summary="データベース統計")
def stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM drug")
    drug_count = c.fetchone()["count"]
    c.execute("SELECT COUNT(*) as count FROM byomei")
    byomei_count = c.fetchone()["count"]
    c.execute("SELECT COUNT(*) as count FROM indication")
    indication_count = c.fetchone()["count"]
    c.execute("SELECT COUNT(DISTINCT yj_code) as count FROM indication")
    mapped_drug_count = c.fetchone()["count"]
    c.execute("SELECT category, COUNT(*) as count FROM drug GROUP BY category ORDER BY count DESC")
    categories = [dict(row) for row in c.fetchall()]
    conn.close()
    return {
        "drug_count": drug_count,
        "byomei_count": byomei_count,
        "indication_count": indication_count,
        "mapped_drug_count": mapped_drug_count,
        "categories": categories,
    }
