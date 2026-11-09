import json
import random
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from backend.domain import BusinessError, cents, evaluate, simulate, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


def seed():
    return json.loads((ROOT / "attachments/sample-data.json").read_text(encoding="utf-8"))


def trade(symbol="A01", side="sell", quantity=100):
    return {"symbol": symbol, "side": side, "quantity": quantity}


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = seed()

    def test_AC01_initial_values(self):
        p = evaluate(self.snapshot)
        self.assertEqual(p["total_assets"], "100000.00")
        self.assertEqual(p["cash"], "20000.00")
        self.assertEqual(p["positions"][0]["weight_pct"], "40.00")
        self.assertEqual(p["industries"][0]["weight_pct"], "60.00")
        self.assertEqual([(w["type"], w["key"]) for w in p["warnings"]], [("instrument", "A01"), ("industry", "科技")])

    def test_AC02_equal_threshold_is_allowed(self):
        p = simulate(self.snapshot, [trade()])["after"]
        self.assertEqual((p["cash"], p["total_assets"]), ("30000.00", "100000.00"))
        self.assertEqual((p["positions"][0]["quantity"], p["positions"][0]["market_value"], p["positions"][0]["weight_pct"]), (300, "30000.00", "30.00"))
        self.assertEqual(p["industries"][0]["weight_pct"], "50.00")
        self.assertEqual(p["warnings"], [])

    def test_AC03_sequential_trades(self):
        p = simulate(self.snapshot, [trade(), trade("A02", "buy", 100)])["after"]
        self.assertEqual((p["cash"], p["total_assets"]), ("25000.00", "100000.00"))
        self.assertEqual((p["positions"][1]["quantity"], p["positions"][1]["market_value"]), (500, "25000.00"))
        self.assertEqual(p["warnings"], [{"type":"industry", "key":"科技", "name":"科技", "actual_pct":"55.00", "threshold_pct":"50.00"}])

    def test_AC04_insufficient_cash(self):
        with self.assertRaises(BusinessError) as error:
            simulate(self.snapshot, [trade(side="buy", quantity=201)])
        self.assertEqual(error.exception.code, "INSUFFICIENT_CASH")

    def test_AC04_oversell(self):
        with self.assertRaises(BusinessError) as error:
            simulate(self.snapshot, [trade(quantity=401)])
        self.assertEqual(error.exception.code, "INSUFFICIENT_HOLDINGS")

    def test_AC04_strict_integer_quantity(self):
        for q in [0, -1, 1.5, 1.0, True, "100", None, 10**12, {}, []]:
            with self.subTest(quantity=q), self.assertRaises(BusinessError) as error:
                simulate(self.snapshot, [trade(quantity=q)])
            self.assertEqual(error.exception.code, "INVALID_QUANTITY")

    def test_failure_does_not_mutate_snapshot_or_previous_result(self):
        original = deepcopy(self.snapshot)
        accepted = simulate(self.snapshot, [trade()])
        saved = deepcopy(accepted)
        with self.assertRaises(BusinessError) as error:
            simulate(self.snapshot, [trade(), trade(quantity=301)])
        self.assertEqual(error.exception.operation_index, 2)
        self.assertEqual(self.snapshot, original)
        self.assertEqual(accepted, saved)
        self.assertEqual(simulate(self.snapshot, [trade()]), accepted)

    def test_sale_can_fund_following_purchase_but_not_prior_purchase(self):
        sell, buy = trade(), trade("A03", "buy", 300)
        self.assertEqual(simulate(self.snapshot, [sell, buy])["after"]["cash"], "0.00")
        with self.assertRaises(BusinessError):
            simulate(self.snapshot, [buy, sell])

    def test_sale_checks_current_holdings(self):
        p = simulate(self.snapshot, [trade("A01", "buy", 1), trade(quantity=401)])["after"]
        self.assertEqual(p["positions"][0]["quantity"], 0)

    def test_sell_all_positions_to_cash(self):
        ops = [trade(i["symbol"], "sell", i["quantity"]) for i in self.snapshot["instruments"]]
        p = simulate(self.snapshot, ops)["after"]
        self.assertEqual((p["cash"], p["holding_count"], p["warnings"]), ("100000.00", 0, []))
        self.assertEqual(sum(Decimal(i["weight_pct"]) for i in p["industries"]), 0)

    def test_threshold_check_precedes_display_rounding(self):
        self.snapshot["instruments"][0]["price"] = "100.01"
        p = simulate(self.snapshot, [trade()])["after"]
        self.assertEqual(p["positions"][0]["weight_pct"], "30.00")
        self.assertTrue(p["positions"][0]["over_limit"])
        self.assertEqual(p["industries"][0]["weight_pct"], "50.00")
        self.assertTrue(p["industries"][0]["over_limit"])

    def test_unknown_symbol_and_side(self):
        for op, code in [(trade("NOPE"), "UNKNOWN_SYMBOL"), (trade(side="hold"), "INVALID_SIDE"), ({}, "INVALID_OPERATION"), ([], "INVALID_OPERATION")]:
            with self.subTest(op=op), self.assertRaises(BusinessError) as error:
                simulate(self.snapshot, [op])
            self.assertEqual(error.exception.code, code)

    def test_operation_limit_and_empty_simulation(self):
        self.assertEqual(simulate(self.snapshot, [])["before"], simulate(self.snapshot, [])["after"])
        with self.assertRaises(BusinessError):
            simulate(self.snapshot, [trade()] * 101)

    def test_money_is_exact_to_cents(self):
        self.assertEqual(cents("0.29"), 29)
        for invalid in ["0.001", "NaN", "Infinity", "-0.01"]:
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                cents(invalid)

    def test_zero_total_has_defined_weights(self):
        self.snapshot["cash"] = "0.00"
        for i in self.snapshot["instruments"]: i["quantity"] = 0
        p = evaluate(self.snapshot)
        self.assertEqual((p["total_assets"], p["cash_weight_pct"], p["warnings"]), ("0.00", "0.00", []))

    def test_invalid_seed_fails_fast(self):
        validate_snapshot(self.snapshot)
        self.snapshot["instruments"][0]["price"] = "0.00"
        with self.assertRaises(ValueError): validate_snapshot(self.snapshot)

    def test_random_valid_sequences_conserve_assets(self):
        rng = random.Random(20261109)
        for case in range(20):
            ops = []
            q = {i["symbol"]: i["quantity"] for i in self.snapshot["instruments"]}
            cash = Decimal(self.snapshot["cash"])
            for _ in range(40):
                item = rng.choice(self.snapshot["instruments"])
                symbol, price = item["symbol"], Decimal(item["price"])
                side = rng.choice(["buy", "sell"])
                maximum = int(cash / price) if side == "buy" else q[symbol]
                if maximum == 0: continue
                quantity = rng.randint(1, maximum)
                ops.append(trade(symbol, side, quantity))
                if side == "buy": cash -= price * quantity; q[symbol] += quantity
                else: cash += price * quantity; q[symbol] -= quantity
            actual = simulate(self.snapshot, ops)["after"]
            with self.subTest(case=case):
                self.assertEqual(actual["total_assets"], "100000.00")
                self.assertEqual(Decimal(actual["cash"]), cash)
                self.assertEqual({p["symbol"]:p["quantity"] for p in actual["positions"]}, q)
