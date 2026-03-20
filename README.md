# drug-indication-db

内科頻用薬95品目＋ツムラ漢方128処方の保険適応病名マッピングDB。

## データソース

- 傷病名マスター（支払基金）27,649件
- PMDA添付文書の効能・効果テキスト

## 使い方

GitHub Pages: `https://<user>.github.io/drug-indication-db/`

### 静的JSON API

| エンドポイント | 内容 |
|---|---|
| `/api/drugs.json` | 薬剤一覧 |
| `/api/drugs/{yj_code}.json` | 薬剤の適応病名 |
| `/api/byomei.json` | 適応病名一覧（薬剤あり） |
| `/api/byomei/{code}.json` | 病名→薬剤の逆引き |
| `/api/mappings.json` | 全マッピング（フラットテーブル） |
| `/api/stats.json` | 統計情報 |

## データ更新

```bash
pip install -r requirements.txt
python src/parse_byomei_master.py   # 傷病名マスター取込
python src/build_db.py              # マッピング構築
python src/export_static.py         # 静的JSON生成
```
