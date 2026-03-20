# drug-indication-db

医療用医薬品の保険適応病名マッピングDB。医薬品マスター全3,278成分をカバー。

https://tomom87.github.io/drug-indication-db/

## 概要

| 項目 | 数値 |
|------|------|
| 総薬剤数（YJ7桁ベース） | 3,647 |
| 手動キュレーション（高精度） | 369（内科頻用薬241＋ツムラ漢方128） |
| 薬効分類ベース（自動） | 3,278 |
| 販売名 | 6,326 |
| 適応マッピング | 2,343 |
| 傷病名マスター | 27,649件 |

## 検索機能

- **一般名**（カタカナ）: アムロジピン、メトホルミン
- **販売名**（商品名）: ノルバスク、フェロミア、ムコスタ
- **ひらがな入力**: あむろじぴん → 自動カタカナ変換で候補表示
- **病名→薬剤の逆引き**: 高血圧症 → 適応のある薬剤一覧

## データソース

- 傷病名マスター（社会保険診療報酬支払基金）
- 医薬品マスター（厚生労働省 レセプト電算処理システム）
- PMDA添付文書の効能・効果テキスト

## 静的JSON API

| エンドポイント | 内容 |
|---|---|
| `/api/drugs.json` | 薬剤一覧（販売名付き） |
| `/api/drugs/{yj_code}.json` | 薬剤の適応病名 |
| `/api/byomei.json` | 適応病名一覧 |
| `/api/byomei/{code}.json` | 病名→薬剤の逆引き |
| `/api/mappings.json` | 全マッピング（フラットテーブル） |
| `/api/stats.json` | 統計情報 |

## データ更新

```bash
pip install -r requirements.txt
python src/parse_byomei_master.py   # 傷病名マスター取込
python src/build_db.py              # 手動キュレーションマッピング構築
python src/build_brand_names.py     # 販売名紐づけ
python src/build_all_drugs.py       # 医薬品マスター全品目追加
python src/export_static.py         # 静的JSON生成
```
