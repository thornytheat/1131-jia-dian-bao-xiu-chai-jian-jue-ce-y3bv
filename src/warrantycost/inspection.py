"""拆检判定：离线和线上授权共用的唯一规则。

授权单、阈值回放和月龄段回放都必须调用这一个函数，避免「回放里该拆、线上却不拆」
或反过来的口径漂移。
"""


def inspection_required(risk, cost_cents, inspection_fee, distance, *, threshold, distance_limit):
    """按预期换件浪费判断是否先拆检。

    工况超过历史半径时一律不自动拆检（交给分诊），否则风险达到阈值且
    预期浪费（风险 × 估算成本）严格大于拆检费时才拆检。
    """
    if distance > distance_limit:
        return False
    return risk >= threshold and risk * cost_cents > inspection_fee
