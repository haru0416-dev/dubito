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

dubito はその一文から速い設計を**導き出さない**。物語にも目的にもなっていない。

モデルがやること（ほぼ常に）はホットパスの近くだけを触ることである。キャッシュ、`max_examples` を減らす、検証層を落とす。それは `properties.local_optimality` が疑う局所点と同じで、双対や残差の天井は聞いていない。

測れる量（時間、層、メモリ）と壊してはいけない制約（`code_ok`、同じ判定）を物語にしたときだけ、トレードオフを独立な `formulation()` として書いて `dubito_check` できる。近傍に良い点があれば `disagree`。双対を超えた主張は制約を落としている。`agree` でも天井以上は言わない。

## やってはいけないこと

- YAML `verification` を定式化に import / コピーする
- 一つの IR から全ソルバーを機械生成する
- `agree` を大域最適の証明として話す（`agent.ceiling` が上限）
- 「重い」への応答として、近くの関数だけを速くして大域改善だと言う
