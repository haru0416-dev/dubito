# P3 以降の設計（構築メモ）

作成日: 2026-08-19。Phase 0–2 は LP/MILP の検証パイプラインを固定した。ここからはクラスを増やすが、**IR からソルバーコードを生成しない**原則は崩さない。

ルーターが選ぶのは「どのソルバーで解くか」ではない。定式化はこれまで通り独立に書かれた `formulation()` である。ルーターが選ぶのは **どの検証層を走らせ、何を保証しないと明示するか**。

## 固定する境界

| する | しない |
|---|---|
| クラス → 検証プロファイル | クラス → CVXPY/Pyomo への機械変換 |
| 検証 IR（linear / residual）は verifier 専用 | 定式化モジュールが YAML `verification` を import |
| 検証強度を構造化 (`layers` + ceiling) | 「一致したので最適」と省略 |
| バックエンドは任意依存 (`[nlp]` は SciPy 既存、Optuna 等は extra) | P3 で 6 ソルバーを全部本依存にする |
| LLM はプロセス外 | 内蔵モデル呼び出し |

PLAN のリスク「スコープ肥大」に従い、実装スライスは次のとおり。

| スライス | 中身 | この PR |
|---|---|---|
| **P3a** | クラスカタログ、ルーター、強度天井、`nlp` 残差 IR、SciPy アダプタ、Rosenbrock プローブ | やる |
| **P3b** | `sat`（CP-SAT ↔ Z3 を対等な検査） | プロファイルのみ。層は未実装 |
| **P3c** | `blackbox` / Optuna、`symbolic_regression` / PySR | プロファイルのみ。optional extra 名だけ予約 |
| **P3d** | `convex` の KKT、`multiobjective` の支配関係、`routing` | プロファイルのみ |
| **P4** | 対話面（MCP ツール記述）とループ面（evaluator）。決定性 `seed` | ツール JSON と CLI。MCP SDK はまだ入れない |
| **P5** | アーカイブ → `dubito.lessons/v1` | distiller。プロンプト注入は外部 |

## クラスと検証天井

コード上の単一の情報源は `dubito.classes.PROFILES`。

| class | 既定の層 | 天井（これ以上は嘘にしない） |
|---|---|---|
| `lp` | exchange, smt, dual, properties | LP 双対が閉じれば強双対 |
| `milp` | 同上 | 整数実行可能かつ dual 一致なら IP 最適。ギャップは証明書ではない |
| `nlp` | exchange, residual, properties | 残差と局所近傍。大域最適の証明ではない。線形双対は走らせない |
| `convex` | exchange, residual, kkt | KKT 未実装の間は残差まで。双対ギャップは後続 |
| `sat` | exchange, smt | 両エンコーディングは対等。未実装 |
| `blackbox` | properties | 交換検査の「最適一致」は弱信号。未実装バックエンド |
| `symbolic_regression` | holdout, properties | ホールドアウト未実装 |
| `multiobjective` | dominance | 未実装 |
| `routing` | exchange | MILP との交換は後続 |

層の状態はスコアの `layers` に `ran` / `skipped:<reason>` で出す。`verification_strength` は `ran` の `+` 連結（P2 互換）。

`guarantee` には ceiling を必ず残す。黒箱で dual_closed を出さない。

## 検証 IR の種類

`verification.kind`（省略時 `linear`）。

- `linear` — P1/P2。Z3・双対・資源単調性。`lp`/`milp` のみ。
- `residual` — 安全な算術式の残差。`nlp`（と後の convex）。Z3 非線形実数は不完全なので **P3a では SMT しない**。

式は `ast` でホワイトリスト（`+ - * / **`、変数名、`abs`/`sqrt`）。`eval` で任意コードは実行しない。

ソルバー定式化はこの式を import しない。物語が定式化の入力、式は独立な証人。

## バックエンド

`dubito.backends` は **ランタイムの薄いアダプタ** であり、IR コンパイラではない。

| アダプタ | 状態 | 隔離 |
|---|---|---|
| CVXPY, OR-Tools | P1 | プロセス分離必須（HiGHS 衝突） |
| SciPy `minimize` | P3a | 同居可。既定サンドボックスは維持 |
| Pyomo / Optuna / PySR / pymoo | 予約 | extra 名のみ。未 import |

`capabilities()` は「このクラスで独立定式化してよい家族」の助言であり、実行するソルバーの選択ではない。

## P4 — 二つの顔

同じ関数を三つの入口から呼ぶ。入口ごとに別の判定ロジックを持たない。

1. **ライブラリ / CLI** — `verify`, `run_cegis`, `check`（既存）
2. **OpenEvolve** — `dubito.evaluator.evaluate`（既存）。`combined_score` は `agree` のみ 1
3. **対話 (MCP)** — ツールは CLI の別名。SDK 無しで `python -m dubito tools` が JSON descriptor を出す。実装は `dubito.faces.TOOLS`

決定性: 問題 YAML の `determinism.seed`（省略 0）は検証層（Hypothesis は既に derandomize）のシード。定式化は YAML を読まないので、SciPy 側の `seed` は各モジュールが自分で持つ。

## P5 — アーカイブから教訓

`dubito.archive/v1` は既に `narrative_hash` / `verification_hash` で join できる。P5 は LLM を呼ばず、同じハッシュの `kind` を数えて `dubito.lessons/v1` にする。

外部エージェントが定式化プロンプトに入れる素材。ツール内でプロンプトを書き換えない。

## 意図的に後回し

- Optuna/PySR/Pyomo の本実装と依存追加
- 超越関数の SMT（dReal）
- KKT / パレート被覆 / routing 交換
- 自然言語を唯一の入力にすること
- 内蔵 LLM
