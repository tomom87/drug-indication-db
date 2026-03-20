"""PMDAの添付文書検索から効能・効果テキストを取得する.

PMDAの検索APIを利用して、薬剤名から添付文書を取得し、
効能・効果セクションを抽出する。
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "pmda_cache"
CACHE_DIR.mkdir(exist_ok=True)

PMDA_SEARCH_URL = "https://www.pmda.go.jp/PmdaSearch/iyakuSearch/"
PMDA_DETAIL_BASE = "https://www.pmda.go.jp"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ja,en;q=0.9",
})


def search_drug(drug_name: str) -> list[dict]:
    """PMDAで薬剤名を検索し、結果リストを返す."""
    cache_file = CACHE_DIR / f"search_{drug_name}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    # PMDA検索はPOSTリクエスト
    # まず検索ページを取得してCSRFトークン等を取る
    try:
        resp = SESSION.get(PMDA_SEARCH_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  検索ページ取得エラー: {e}")
        return []

    # フォームパラメータを構築
    params = {
        "screenId": "400",
        "action": "search",
        "iYakuName": drug_name,
        "iYakuKbn": "1",  # 医療用医薬品
        "iPageNo": "1",
        "iPageSize": "10",
    }

    try:
        resp = SESSION.post(PMDA_SEARCH_URL, data=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  検索エラー ({drug_name}): {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    # 検索結果テーブルからリンクを抽出
    for link in soup.select("a[href*='go/pack/']"):
        href = link.get("href", "")
        name = link.get_text(strip=True)
        if href:
            full_url = href if href.startswith("http") else PMDA_DETAIL_BASE + href
            results.append({"name": name, "url": full_url})

    # 代替: info.pmda.go.jp のリンク
    if not results:
        for link in soup.select("a[href*='info.pmda.go.jp']"):
            href = link.get("href", "")
            name = link.get_text(strip=True)
            if href and "pack" in href:
                results.append({"name": name, "url": href})

    cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    time.sleep(1)  # rate limit
    return results


def fetch_indication_from_page(url: str) -> str | None:
    """添付文書ページから効能・効果テキストを抽出する."""
    cache_key = re.sub(r"[^\w]", "_", url)
    cache_file = CACHE_DIR / f"page_{cache_key[:80]}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ページ取得エラー: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    indication_text = ""

    # パターン1: XMLベースの新しい添付文書
    for section in soup.find_all(["div", "section"]):
        heading = section.find(["h1", "h2", "h3", "h4", "b", "strong"])
        if heading and re.search(r"効能.*効果|適応", heading.get_text()):
            # 次のセクションまでのテキストを取得
            indication_text = section.get_text(separator="\n", strip=True)
            break

    # パターン2: テキストから正規表現で抽出
    if not indication_text:
        full_text = soup.get_text()
        match = re.search(
            r"[【\[]?\s*効能[又はまたは・]*効果\s*[】\]]?\s*\n?([\s\S]*?)(?=[【\[]\s*[用法用量|使用上|薬効|効能又は効果に関連する])",
            full_text,
        )
        if match:
            indication_text = match.group(1).strip()

    if indication_text:
        # テキストクリーンアップ
        indication_text = re.sub(r"\s+", " ", indication_text).strip()
        cache_file.write_text(indication_text, encoding="utf-8")
        time.sleep(0.5)
        return indication_text

    time.sleep(0.5)
    return None


def fetch_indication_info_pmda(drug_name: str) -> str | None:
    """info.pmda.go.jpの添付文書情報メニューから直接検索する."""
    cache_file = CACHE_DIR / f"info_{drug_name}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data.get("indication")

    # info.pmda.go.jp の検索URL
    search_url = "https://www.info.pmda.go.jp/psearch/html/menu_tenpu_base.html"

    try:
        # 直接的にパッケージインサート検索
        params = {"shinryouyouiyakuhin": drug_name}
        resp = SESSION.get(
            "https://www.info.pmda.go.jp/go/search/",
            params=params,
            timeout=30,
        )
    except Exception:
        pass

    return None


def main():
    """テスト: いくつかの薬剤で検索を試す."""
    test_drugs = ["アムロジピン", "ツムラ葛根湯"]
    for drug in test_drugs:
        print(f"\n--- {drug} ---")
        results = search_drug(drug)
        print(f"  検索結果: {len(results)} 件")
        for r in results[:3]:
            print(f"  - {r['name']}: {r['url']}")

        if results:
            indication = fetch_indication_from_page(results[0]["url"])
            if indication:
                print(f"  効能・効果: {indication[:200]}...")


if __name__ == "__main__":
    main()
