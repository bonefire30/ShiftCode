# 单文件 Benchmark 三次运行汇总

本报告汇总了 `benchmark_dataset` 单文件 Java-to-Go benchmark 连续三次完整运行的结果，用于评估当前单文件迁移能力的稳定性与阶段完成度。

## 结论

- 三次运行均为 `8/8` 全通过
- 三次运行均无 `fatal`、无 `exception`
- 三次运行所有 case 最终都满足：
  - `last_build_ok = true`
  - `last_test_ok = true`
  - `test_gen_ok = true`
  - `test_quality_ok = true`
- 当前单文件 benchmark 已具备初步稳定性，可作为后续多文件阶段的回归基线

## 总览表

| 运行 | 报告文件 | 总耗时 (s) | 总数 | 通过 | 失败 |
|---|---|---:|---:|---:|---:|
| 第 1 次 | `run_logs/benchmark_suite_20260425_194932.json` | 438.512 | 8 | 8 | 0 |
| 第 2 次 | `run_logs/benchmark_suite_20260425_202333.json` | 434.260 | 8 | 8 | 0 |
| 第 3 次 | `run_logs/benchmark_suite_20260425_203142.json` | 357.026 | 8 | 8 | 0 |

## 每个 Case 耗时对比

| Case | 第 1 次 (s) | 第 2 次 (s) | 第 3 次 (s) | 三次结果 |
|---|---:|---:|---:|---|
| `tier1_basic/01_lru_cache` | 36.877 | 48.605 | 43.318 | 通过 / 通过 / 通过 |
| `tier2_oop/01_user_service` | 41.913 | 52.031 | 54.733 | 通过 / 通过 / 通过 |
| `tier3_concurrency/01_downloader` | 24.853 | 25.150 | 23.678 | 通过 / 通过 / 通过 |
| `tier4_generics/01_result_wrapper` | 43.494 | 32.319 | 35.529 | 通过 / 通过 / 通过 |
| `tier5_polymorphism/01_payment_processor` | 179.005 | 159.574 | 75.876 | 通过 / 通过 / 通过 |
| `tier6_streams/01_data_analyzer` | 31.434 | 32.585 | 27.875 | 通过 / 通过 / 通过 |
| `tier7_exceptions/01_retry_executor` | 45.674 | 53.056 | 62.932 | 通过 / 通过 / 通过 |
| `tier8_io_json/01_config_parser` | 35.255 | 30.933 | 33.080 | 通过 / 通过 / 通过 |

## 稳定性观察

### 1. 通过率稳定

三次完整运行均为 `8/8` 全通过，说明当前单文件 Java-to-Go pipeline 已不再是偶发性跑通，而是开始具备重复可验证性。

### 2. 总耗时整体稳定，并在第三次显著下降

- 第 1 次：`438.512s`
- 第 2 次：`434.260s`
- 第 3 次：`357.026s`

前两次总耗时接近，第三次整体更快，说明系统在当前样例集上的收敛效率没有恶化，反而有改善趋势。

### 3. 最慢 Case 仍是 tier5，但抖动已经明显下降

`tier5_polymorphism/01_payment_processor` 是三次运行里始终最慢的 case：

- 第 1 次：`179.005s`
- 第 2 次：`159.574s`
- 第 3 次：`75.876s`

这说明 tier5 仍然是当前单文件 benchmark 中最值得关注的性能波动点，但它已经从早期的明显长尾，收敛到了更可接受的区间。

### 4. 所有 Case 最终状态都很干净

三次报告中，每个 case 都满足：

- `status = passed`
- `fatal = ""`
- `exception = ""`
- `repair_round = 0`

这说明从 benchmark 汇总视角看，没有残留的错误态或异常态。

## 阶段判断

基于这三次结果，可以给出当前阶段判断：

- 单文件 Java-to-Go 功能已经完成第一轮验证
- 当前 8 个单文件 case 可以正式作为回归基线保留
- 系统主研发重心可以转向多文件项目 benchmark

更准确地说，当前状态并不意味着单文件问题已经“彻底结束”，而是意味着单文件能力已经不再是当前主瓶颈。

## 建议后续动作

1. 固化当前 8 个单文件 case 为 regression suite
2. 每次改动多文件工作流后，重新跑这 8 个单文件 benchmark
3. 启动 `benchmark_projects/wave1/` 的多文件项目集建设
4. 持续跟踪 tier5 等长耗时 case 的收敛效率
