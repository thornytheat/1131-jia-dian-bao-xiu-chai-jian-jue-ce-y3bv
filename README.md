# 家电保修拆检决策

面向保修主管的本地工作台。内置业务样例覆盖家电保修成本预测、拆检阈值与备件分配。样例采用确定性构造，适合复现实验和核查边界行为。

## 启动

```sh
docker compose up --build -d
```

打开 `http://127.0.0.1:18210/` 查看配件授权单。左侧六个入口可展开运行证据。调整「备件额度」，点击「重新授权」比较处置结果。结束后执行 `docker compose down --remove-orphans`。

## 独立业务模块

- 保修单 `warranty_claims`
- 机型映射 `model_aliases`
- 返修样本 `repair_cohorts`
- 成本拟合 `claim_cost_model`
- 配件授权 `parts_authorization`
- 维修结算 `service_balance`

## 查看运行结果

- `GET /api/overview` 返回默认运行及其指纹。
- `POST /api/scenario` 接收 `{"capacity": 3}`。入口接受 1–100 的整数，应用样例时使用该业务额度。
- `GET /api/stages/service_balance` 查看该环节的独立证据，支持 `?capacity=3`。

```sh
docker compose exec -T app python -m warrantycost.delivery evaluate --capacity 3
docker compose exec -T app pytest -q
```

数据和模型约定见 [业务契约](docs/SPEC.md)。模块、例外规则与验证入口见 [业务深度](docs/DEPTH.md)。
