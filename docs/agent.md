# 外部モデル向けの使い方

dubito は LLM を内蔵しない。**検証対象は定式化コード**（`formulation()` モジュール）である。モデルはプロセスの外でモジュールを書き、スコアを読む。汎用の Python 検証器ではない。

## ループ

1. `dubito_spec` — 物語・変数名・クラス・天井。**検証 IR は返さない**。
2. `dubito_contract` — `formulation()` の形とスケルトン。制約は物語から書く。
3. バックエンドを **2 つ以上、独立に** 書く（同じ制約行列のコピーは禁止）。
4. `dubito_check` — まずソース（IR import 禁止）、それからソルバー。既定 compact。`agent.next` / `agent.repair` / `agent.ceiling` を読む。
5. `disagree` なら指名されたモジュールを物語から書き直す。`agree` なら止まり、天井以上を主張しない。

## Cursor / Claude Desktop

SDK 無し。stdio は JSON-RPC（Content-Length）。

```json
{
  "mcpServers": {
    "dubito": {
      "command": "python",
      "args": ["-m", "dubito", "mcp"]
    }
  }
}
```

作業ディレクトリは dubito を `pip install -e .` した環境。問題 YAML と定式化パスは絶対パスが安全。

## CLI の別名

```bash
python -m dubito playbook
python -m dubito spec --problem probes/phase0/furniture.yaml
python -m dubito contract --problem probes/phase0/furniture.yaml
python -m dubito call dubito_spec --args '{"problem":"probes/phase0/furniture.yaml"}'
python -m dubito tools
```

`check` の CLI は今まで通りフルのスコアベクトル。ツール / MCP の `dubito_check` は既定 compact。

## 「この機能、重い」と言われたとき

速い設計を dubito が発明するわけではない。局所に閉じない**手続き**が解決法である。

1. ホットパスの編集を止める。
2. `dubito_spec` — 「重い」を目的（時間・層・メモリ）にし、壊してはいけないものを制約にする。
3. **別系統**の `formulation()` を2本。同じループにキャッシュを二つ足すのは1本である。
4. `dubito_check`。`local_optimality` なら incumbent を捨てる（`agent.next` は `discard_and_rewrite`、`from: dubito_spec`）。
5. `agree` かつ `agent.next.exhausted`（双対が閉じた）なら、この IR ではもう良くならないので止まる。
6. `agree` でもギャップや NLP 天井なら、まだ局所かもしれない。それ以上は主張しない。

LP なら双対が閉じれば大域（その IR に対して）。コードの速さは、アルゴリズム族の離散選択に落とさない限り NLP と同じで、近傍探索だけでは終わらない。

## やってはいけないこと

- YAML `verification` を定式化に import / コピーする
- 一つの IR から全ソルバーを機械生成する
- `agree` を大域最適の証明として話す（`agent.ceiling` が上限）
- 「重い」への応答として、近くの関数だけを速くして大域改善だと言う
