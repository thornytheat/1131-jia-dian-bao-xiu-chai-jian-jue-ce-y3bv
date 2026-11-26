# 家电保修拆检决策功能与验证

领域为 AI/ML / 传统ML。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 保修单 | 核保时点、筛出安全风险、把重复序列号送复核 | 运行证据第 1 段 | `src/warrantycost/warranty_claims/contracts.py` `src/warrantycost/warranty_claims/analysis.py` `src/warrantycost/warranty_claims/service.py` | `tests/test_warranty_claims.py` |
| M2 机型映射 | 用生效版本解析兼容件，阻断重叠版本 | 运行证据第 2 段 | `src/warrantycost/model_aliases/contracts.py` `src/warrantycost/model_aliases/analysis.py` `src/warrantycost/model_aliases/service.py` | `tests/test_model_aliases.py` |
| M3 返修样本 | 拆分可见、验证与不可使用的工单 | 运行证据第 3 段 | `src/warrantycost/repair_cohorts/contracts.py` `src/warrantycost/repair_cohorts/analysis.py` `src/warrantycost/repair_cohorts/service.py` | `tests/test_repair_cohorts.py` |
| M4 成本拟合 | 按产品系列拟合成本和换件无效概率 | 运行证据第 4 段 | `src/warrantycost/claim_cost_model/contracts.py` `src/warrantycost/claim_cost_model/analysis.py` `src/warrantycost/claim_cost_model/service.py` | `tests/test_claim_cost_model.py` |
| M5 配件授权 | 按拆检费、预期浪费和实际库存批准 | 运行证据第 5 段 | `src/warrantycost/parts_authorization/contracts.py` `src/warrantycost/parts_authorization/analysis.py` `src/warrantycost/parts_authorization/service.py` | `tests/test_parts_authorization.py` |
| M6 维修结算 | 核对结算组成与不可重复消费的授权额度 | 运行证据第 6 段 | `src/warrantycost/service_balance/contracts.py` `src/warrantycost/service_balance/analysis.py` `src/warrantycost/service_balance/service.py` | `tests/test_service_balance.py` |

## 陷阱登记

| TRAP | 输入情形 | 错误风险 | 处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-25 | 同一别名在两个生效版本重叠 | 机型取值受导入先后影响 | 冻结该别名并留下冲突 | `src/warrantycost/model_aliases/analysis.py` | `tests/test_model_aliases.py::test_catalogue_overlap_blocks_guessing` |
| TRAP-26 | 安全标记旧修订迟到 | 重新流入自动裁决 | 最高版本单据覆盖 | `src/warrantycost/warranty_claims/analysis.py` | `tests/test_warranty_claims.py::test_older_snapshot_cannot_undo_safety_flag` |
| TRAP-31 | 拟合线上可能出现极端 logit | 指数溢出 | 对负绝对值求指数 | `src/warrantycost/claim_cost_model/analysis.py` | `tests/test_claim_cost_model.py::test_sigmoid_uses_stable_exponent` |
| TRAP-32 | 同批次相同或近同平均值 | 归一时除零或浮点抵消 | 先中心化并设下限 | `src/warrantycost/claim_cost_model/analysis.py` | `tests/test_claim_cost_model.py::test_zero_variance_does_not_shift_cost_prediction` |
| TRAP-42 | 工单事件日期和真正落盘日期不同 | 回测错读迟到完工结果 | 重放闭单日和发布日的较晚值 | `src/warrantycost/repair_cohorts/analysis.py` | `tests/test_repair_cohorts.py::test_late_historical_writeback_never_seen_by_training` |
| TRAP-43 | 回放没有换件失败案例 | 召回率误显示为满分或崩溃 | 显式返回未知召回 | `src/warrantycost/claim_cost_model/analysis.py` | `tests/test_claim_cost_model.py::test_no_positive_repairs_reports_unknown_recall` |
| TRAP-44 | 未见过工况恰好给低返修风险 | 无保护地批准更换 | 按训练统计量给分布外门槛 | `src/warrantycost/parts_authorization/analysis.py` | `tests/test_parts_authorization.py::test_high_confidence_outlier_is_never_automatically_approved` |
| TRAP-53 | 把稀有工况放进评估批次 | 同单得到随同批其他单变化的打分 | 按固定模型逐条执行 | `src/warrantycost/claim_cost_model/analysis.py` | `tests/test_claim_cost_model.py::test_prediction_not_affected_by_other_service_case` |
