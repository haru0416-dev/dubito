# 自己適用レポート

日付: 2026-08-19  
コマンド: `python -m dubito self`  
仮説: **検証層の内部 LP（IR 双対と局所近傍箱）は、独立定式化のクロスチェックに耐える。SciPy `dual.py` の境界はそれと一致する。**

## 結果

**成立。** `hypothesis_holds: true`。`python3 -m pytest` は 94 passed（うち自己適用 8）。

| ケース | 期待 | 判定 | 目的 |
|---|---|---|---|
| 双対 GLPK vs GLOP | agree | agree | 220 / 220 |
| 被覆を `≤` に逆転 | disagree | disagree | 220 vs 0 |
| 近傍箱 CVXPY vs CBC | agree | agree | 220 / 220、点 `(2, 6)` |
| 近傍でミックス逆転 | disagree | disagree | 実行不能 vs 220 |

SciPy HiGHS の双対: `wood≈10, labor≈10, mix=0`、境界 220、相補スラック成立。この価格を独立な GLPK / GLOP 定式化に代入しても実行可能で、目的は 220。

ルーターはクラス表のまま。時間予算ナップサックにはしていない。

## 見つかった実装バグ

近傍 MILP は整数変数を `nonneg=True` なしで切った。交換検査で OR-Tools の `2.0` を CVXPY に入れると、CVXPY 1.9 の `project()` が Python `float` を拒否した。家具定式化は `nonneg=True` があり、隠れていた。

修正: `cvxpy_backend.check` が `np.asarray(value)` を代入する。自己適用が検証器の相関バグ（単一経路でしか通らない代入）を拾った例。

## これが示さないこと

- `dual.py` を複数ソルバーのコンパイラに変えたわけではない。SciPy はそのまま。独立定式化はプローブ。
- 大域的な検証器の正しさの証明ではない。家具 IR の双対と、半径 2 の箱だけ。
- LLM 定式化ではない。
