"""Pure calculations. All balances are integer cents; input snapshots stay untouched."""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

ENGINE_VERSION = "1"
MAX_OPERATIONS = 100


class BusinessError(Exception):
    def __init__(self, code, message, *, status=422, field=None, operation_index=None):
        self.code, self.message, self.status = code, message, status
        self.field, self.operation_index = field, operation_index
        super().__init__(message)

    def payload(self):
        return {"error": {"code": self.code, "message": self.message,
                          "field": self.field, "operation_index": self.operation_index}}


def cents(value):
    number = Decimal(str(value))
    if not number.is_finite() or number < 0 or number * 100 != (number * 100).to_integral_value():
        raise ValueError("金额必须为非负且至多两位小数")
    return int(number * 100)


def money(value):
    return f"{Decimal(value) / 100:.2f}"


def percent(value, total):
    if total == 0:
        return "0.00"
    return str((Decimal(value) * 100 / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def exceeds(value, total, threshold):
    # Compare exact integers, before rounding or dividing. Equality is allowed.
    numerator, denominator = Decimal(threshold).as_integer_ratio()
    return value * denominator > total * numerator


def validate_snapshot(snapshot):
    if snapshot["currency"] != "CNY":
        raise ValueError("仅支持 CNY")
    cents(snapshot["cash"])
    seen = set()
    for item in snapshot["instruments"]:
        if not item["symbol"] or item["symbol"] in seen:
            raise ValueError("标的代码重复或为空")
        seen.add(item["symbol"])
        if cents(item["price"]) <= 0 or not item["industry"]:
            raise ValueError("必须提供正价格与行业")
        if type(item["quantity"]) is not int or item["quantity"] < 0:
            raise ValueError("初始数量必须为非负整数")
    rules = snapshot["rules"]
    if (rules["comparison"] != "strictly_greater_than" or
            rules["cash_in_denominator"] is not True or rules["cash_in_industry"] is not False or
            rules["quantity"] != "positive_integer" or cents(rules["fees"]) != 0):
        raise ValueError("不支持该计算规则")
    for key in ["single_instrument_threshold", "industry_threshold"]:
        if not Decimal(0) <= Decimal(rules[key]) <= Decimal(1):
            raise ValueError("阈值必须介于 0 和 1")


def evaluate(snapshot, quantities=None, cash=None):
    quantities = quantities if quantities is not None else {i["symbol"]: i["quantity"] for i in snapshot["instruments"]}
    cash = cents(snapshot["cash"]) if cash is None else cash
    total = cash + sum(cents(i["price"]) * quantities[i["symbol"]] for i in snapshot["instruments"])
    rules = snapshot["rules"]
    positions, industries, warnings = [], {}, []
    for item in snapshot["instruments"]:
        value = cents(item["price"]) * quantities[item["symbol"]]
        over = exceeds(value, total, rules["single_instrument_threshold"])
        position = {**item, "quantity": quantities[item["symbol"]], "market_value": money(value),
                    "weight_pct": percent(value, total), "over_limit": over}
        positions.append(position)
        industries[item["industry"]] = industries.get(item["industry"], 0) + value
        if over:
            warnings.append({"type": "instrument", "key": item["symbol"], "name": item["name"],
                             "actual_pct": percent(value, total),
                             "threshold_pct": percent(Decimal(rules["single_instrument_threshold"]), 1)})
    sectors = []
    for name, value in sorted(industries.items(), key=lambda pair: (-pair[1], pair[0])):
        over = exceeds(value, total, rules["industry_threshold"])
        sectors.append({"name": name, "market_value": money(value), "weight_pct": percent(value, total), "over_limit": over})
        if over:
            warnings.append({"type": "industry", "key": name, "name": name,
                             "actual_pct": percent(value, total),
                             "threshold_pct": percent(Decimal(rules["industry_threshold"]), 1)})
    return {"portfolio_id": snapshot["portfolio_id"], "name": snapshot["name"],
            "currency": snapshot["currency"], "snapshot_id": snapshot["snapshot_id"],
            "snapshot_at": snapshot["snapshot_at"], "total_assets": money(total),
            "cash": money(cash), "cash_weight_pct": percent(cash, total),
            "market_value": money(total - cash), "holding_count": sum(q > 0 for q in quantities.values()),
            "positions": positions, "industries": sectors, "warnings": warnings, "rules": deepcopy(rules)}


def simulate(snapshot, operations):
    if not isinstance(operations, list) or len(operations) > MAX_OPERATIONS:
        raise BusinessError("INVALID_OPERATIONS", f"操作列表最多 {MAX_OPERATIONS} 笔", field="operations")
    quantities = {i["symbol"]: i["quantity"] for i in snapshot["instruments"]}
    prices = {i["symbol"]: cents(i["price"]) for i in snapshot["instruments"]}
    cash = cents(snapshot["cash"])
    steps = []
    for index, op in enumerate(operations, start=1):
        def fail(code, message, field=None):
            raise BusinessError(code, f"第 {index} 笔：{message}", field=field, operation_index=index)
        if not isinstance(op, dict) or set(op) != {"symbol", "side", "quantity"}:
            fail("INVALID_OPERATION", "操作必须且只能包含 symbol、side、quantity")
        symbol, side, quantity = op["symbol"], op["side"], op["quantity"]
        if not isinstance(symbol, str) or symbol not in prices:
            fail("UNKNOWN_SYMBOL", "请选择快照中的有效标的", "symbol")
        if side not in ("buy", "sell"):
            fail("INVALID_SIDE", "交易方向只能是 buy 或 sell", "side")
        if type(quantity) is not int or quantity <= 0 or quantity > 1_000_000_000:
            fail("INVALID_QUANTITY", "数量必须是 1 至 1,000,000,000 的正整数", "quantity")
        amount = prices[symbol] * quantity
        if side == "buy":
            if amount > cash:
                fail("INSUFFICIENT_CASH", f"现金不足，需要 ¥{money(amount)}，当前可用 ¥{money(cash)}", "quantity")
            cash -= amount
            quantities[symbol] += quantity
        else:
            if quantity > quantities[symbol]:
                fail("INSUFFICIENT_HOLDINGS", f"可卖数量不足，当前 {symbol} 可卖 {quantities[symbol]} 股", "quantity")
            cash += amount
            quantities[symbol] -= quantity
        steps.append({**op, "index": index, "amount": money(amount), "cash_after": money(cash)})
    before, after = evaluate(snapshot), evaluate(snapshot, quantities, cash)
    if before["total_assets"] != after["total_assets"]:
        raise RuntimeError("模拟前后总资产不守恒")
    return {"before": before, "after": after, "steps": steps, "engine_version": ENGINE_VERSION}
