"""计算 6 道新 hard 题的精确期望值。

仅开发期使用（一次性）：用 numpy/scipy 把每道题的所有 expected_numeric
精确算出来，打印到终端后手工填进 tests/data/test_cases.json。

运行：
    python scripts/_compute_hard_expectations.py
"""

from __future__ import annotations

import numpy as np
from scipy import stats, integrate, optimize


def sep(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


# =============================================================================
# hard_01: 特征值 + 回归 + 积分链
# =============================================================================
sep("hard_01: matrix / regression / integration chain")

M = np.array([[2.0, 1.0, 0.0], [1.0, 2.0, 1.0], [0.0, 1.0, 2.0]])
eigvals = np.sort(np.linalg.eigvalsh(M))
print(f"eigenvalues (ascending) = {eigvals}")
e1, e2, e3 = eigvals
L = e3
print(f"e1={e1:.6f}  e2={e2:.6f}  e3=L={e3:.6f}")

x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
y = np.array([3.46, 6.75, 10.34, 13.59, 17.09])
lr = stats.linregress(x, y)
slope = lr.slope
r2 = lr.rvalue**2
print(f"regression slope = {slope:.6f}   r_squared = {r2:.8f}")

I, _ = integrate.quad(lambda t: L * t, 0.0, 2.0)
print(f"I = integral of L*x dx on [0,2] = {I:.6f}   (theoretical 2L = {2 * L:.6f})")


# =============================================================================
# hard_02: 模型选择（三候选，选最简且 R²>=0.999）
# =============================================================================
sep("hard_02: model selection (linear vs quad vs cubic)")

x2 = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
y2 = np.array([0.1, 0.9, 2.1, 4.2, 7.1, 11.3, 16.8, 23.7, 32.2])


def poly_r2(deg: int) -> float:
    coeffs = np.polyfit(x2, y2, deg)
    y_pred = np.polyval(coeffs, x2)
    ss_res = np.sum((y2 - y_pred) ** 2)
    ss_tot = np.sum((y2 - y2.mean()) ** 2)
    return 1.0 - ss_res / ss_tot, coeffs


r2_lin, _ = poly_r2(1)
r2_quad, c_quad = poly_r2(2)
r2_cub, _ = poly_r2(3)
print(f"R_sq linear = {r2_lin:.8f}")
print(f"R_sq quad   = {r2_quad:.8f}")
print(f"R_sq cubic  = {r2_cub:.8f}")

qualified = [(d, r) for d, r in [(1, r2_lin), (2, r2_quad), (3, r2_cub)] if r >= 0.999]
best_deg = qualified[0][0] if qualified else max([(1, r2_lin), (2, r2_quad), (3, r2_cub)], key=lambda t: t[1])[0]
print(f"best_degree = {best_deg}")

coeffs_best = np.polyfit(x2, y2, best_deg)
y_pred_at_5 = float(np.polyval(coeffs_best, 5.0))
print(f"best coeffs = {coeffs_best}")
print(f"y_pred_at_5 = {y_pred_at_5:.6f}")


# =============================================================================
# hard_03: 完整科研流程（两组 + t 检验 + 柱状图）
# =============================================================================
sep("hard_03: full scientific workflow (two-sample comparison)")

C = np.array([45.2, 47.1, 44.8, 46.5, 45.9, 47.3, 44.7, 46.1])
T = np.array([48.5, 49.2, 50.1, 47.9, 49.7, 50.3, 48.2, 49.4])

mean_C, mean_T = C.mean(), T.mean()
diff = mean_T - mean_C
t_stat, p_val = stats.ttest_ind(T, C, equal_var=True)
print(f"mean_C = {mean_C:.6f}   mean_T = {mean_T:.6f}   diff = {diff:.6f}")
print(f"t_statistic (T vs C) = {t_stat:.6f}   p_value = {p_val:.6f}")


# =============================================================================
# hard_04: 多层依赖（求根 -> 积分 -> 序列 -> 统计）
# =============================================================================
sep("hard_04: nested dependency (root -> integral -> sequence -> stats)")

r = optimize.brentq(lambda t: t**3 + t - 10.0, 1.0, 3.0, xtol=1e-12)
print(f"root r of x^3 + x - 10 in [1, 3] = {r:.8f}")

I4, _ = integrate.quad(lambda t: t * np.exp(-t), 0.0, r)
print(f"I = integral of x*exp(-x) dx on [0, r] = {I4:.8f}")

k = round(I4, 4)
s = np.array([k * i for i in range(1, 7)], dtype=float)
mean_s = s.mean()
std_s = s.std(ddof=0)  # population std, matches descriptive_statistics default
std_s_sample = s.std(ddof=1)
print(f"k (I rounded to 4 dp) = {k}")
print(f"s = {s}")
print(f"mean_s = {mean_s:.6f}")
print(f"std_s (pop, ddof=0)    = {std_s:.6f}")
print(f"std_s (sample, ddof=1) = {std_s_sample:.6f}")


# =============================================================================
# hard_05: 异常恢复 + 链式（含噪线性 + outlier 检测）
# =============================================================================
sep("hard_05: outlier detection and re-fit")

x5 = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
y5 = np.array([2.1, 4.2, 5.9, 100.0, 10.3, 12.1, 14.0, 15.9, 18.2, 20.1])
lr_full = stats.linregress(x5, y5)
r2_full = lr_full.rvalue**2
print(f"R_sq (full, with outlier) = {r2_full:.6f}")

med = float(np.median(y5))
dev = (y5 - med) ** 2
idx_out = int(np.argmax(dev))
outlier_value = float(y5[idx_out])
print(f"median(y) = {med}   outlier idx = {idx_out}   outlier value = {outlier_value}")

x5c = np.delete(x5, idx_out)
y5c = np.delete(y5, idx_out)
lr_clean = stats.linregress(x5c, y5c)
slope_clean = lr_clean.slope
r2_clean = lr_clean.rvalue**2
print(f"slope_clean = {slope_clean:.6f}   R_sq_clean = {r2_clean:.8f}")


# =============================================================================
# hard_06: 协同规划（三组数据两两相关 + 热力图 + 最弱相关对 t 检验）
# =============================================================================
sep("hard_06: multi-dataset correlation planning")

A = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
B = np.array([3.0, 1.0, 4.0, 2.0, 5.0, 6.0])
C6 = np.array([6.0, 5.0, 7.0, 4.0, 8.0, 3.0])

r_AB = float(np.corrcoef(A, B)[0, 1])
r_AC = float(np.corrcoef(A, C6)[0, 1])
r_BC = float(np.corrcoef(B, C6)[0, 1])
print(f"r_AB = {r_AB:.6f}   r_AC = {r_AC:.6f}   r_BC = {r_BC:.6f}")

# 对内置对：选绝对值最小的
pairs = {"AB": (abs(r_AB), A, B), "AC": (abs(r_AC), A, C6), "BC": (abs(r_BC), B, C6)}
weakest_pair_name = min(pairs, key=lambda k: pairs[k][0])
min_abs_r = pairs[weakest_pair_name][0]
p1, p2 = pairs[weakest_pair_name][1], pairs[weakest_pair_name][2]
t6, pv6 = stats.ttest_ind(p1, p2, equal_var=True)
print(f"weakest pair = {weakest_pair_name}   |r| = {min_abs_r:.6f}")
print(f"t_statistic on ({weakest_pair_name}) = {t6:.6f}   p = {pv6:.6f}")
