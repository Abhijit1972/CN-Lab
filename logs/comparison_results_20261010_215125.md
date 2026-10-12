# Adaptive vs. Fixed Threshold – Comparison Results

- **Adaptive CSV**: `logs/test_synthetic.csv`
- **Fixed CSV**:    `logs/test_synthetic_fixed.csv`

## Summary

| Metric | Adaptive | Fixed |
|--------|:--------:|:-----:|
| Active windows analysed | 105 | 105 |
| NORMAL windows | 90 | 92 |
| WARNING windows | 2 | 2 |
| CONGESTED windows | 13 | 11 |
| **False positives** (vs. other method) | **2** | **0** |
| Congestion events detected | 1 | 1 |
| Agreement rate | 96.2 % | – |
| Matched congestion events | 1 | – |
| Avg detection delay | -2.0 s | – |

> **Detection delay**: positive = adaptive detected the event *later* than fixed;
> negative = adaptive detected it *earlier*.  A near-zero or negative value
> alongside a lower false-positive count proves the adaptive method's advantage.

## Congestion Event Details

| Event | Adp start (s) | Adp dur (s) | Fix start (s) | Fix dur (s) | Delay (s) | Matched |
|-------|:-------------:|:-----------:|:-------------:|:-----------:|:---------:|:-------:|
| 1 | 60 | 13 | 62 | 11 | -2 | YES |

## Interpretation

- A **lower false-positive count** means the method raises fewer nuisance alerts.
- The adaptive method's false-positive count should be lower because it raises
  the threshold proportionally to measured normal traffic.
- The fixed method may produce many false positives on high-baseline machines
  (e.g. a 4K stream counts as congestion even on an otherwise healthy connection).
- If the detection delay for the adaptive method is ≤ 0, it detects congestion
  at least as fast as the fixed method.
