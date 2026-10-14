"""
Tests for the budget-based restocking recommendations.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "server"))

from restock import build_restock_plan, compute_monthly_demand, demand_window


def inv(sku, qoh, rp, cost, warehouse="Tokyo", category="Sensors"):
    return {"sku": sku, "name": sku, "category": category, "warehouse": warehouse,
            "quantity_on_hand": qoh, "reorder_point": rp, "unit_cost": cost}


def order(date, *lines):
    return {"order_date": f"{date}T10:00:00",
            "items": [{"sku": s, "name": s, "quantity": q, "unit_price": 1} for s, q in lines]}


class TestDemandWindow:
    def test_anchors_on_latest_month(self):
        orders = [order("2025-03-05", ("A", 1)), order("2025-06-05", ("A", 1))]
        assert demand_window(orders, 3) == ["2025-04", "2025-05", "2025-06"]

    def test_crosses_year_boundary(self):
        orders = [order("2025-01-05", ("A", 1))]
        assert demand_window(orders, 3) == ["2024-11", "2024-12", "2025-01"]

    def test_monthly_demand_averages_over_lookback(self):
        orders = [order("2025-06-01", ("A", 30)), order("2025-05-01", ("A", 30)),
                  order("2025-01-01", ("A", 999))]
        assert compute_monthly_demand(orders, 3) == {"A": 20.0}


class TestBuildPlan:
    def plan(self, inventory, orders, budget, forecasts=(), **kw):
        return build_restock_plan(inventory, orders, list(forecasts), budget, **kw)

    def test_trend_applied_only_with_forecast(self):
        orders = [order("2025-06-01", ("A", 30), ("B", 30))]
        fc = [{"item_sku": "A", "current_demand": 100, "forecasted_demand": 200}]
        p = self.plan([inv("A", 0, 0, 1), inv("B", 0, 0, 1)], orders, 1e6,
                      fc, lookback_months=1)
        by = {r["sku"]: r for r in p["recommendations"]}
        assert by["A"]["trend_factor"] == 2.0 and by["B"]["trend_factor"] == 1.0
        assert by["A"]["target_level"] == 60 and by["B"]["target_level"] == 30

    def test_sufficient_items_excluded_and_target_at_least_reorder_point(self):
        orders = [order("2025-06-01", ("A", 30))]
        p = self.plan([inv("A", 500, 10, 1), inv("B", 5, 50, 1)], orders, 1e6,
                      lookback_months=1)
        assert p["items_sufficient"] == 1
        assert [r["sku"] for r in p["recommendations"]] == ["B"]
        assert p["recommendations"][0]["need_qty"] == 45

    def test_priority_order(self):
        orders = [order("2025-06-01", ("A", 300), ("B", 30), ("C", 3000))]
        inventory = [inv("A", 100, 10, 1), inv("B", 5, 10, 1), inv("C", 100, 10, 1),
                     inv("Z", 0, 5, 1)]
        p = self.plan(inventory, orders, 1e6, lookback_months=1)
        # below-reorder first (B by cover, Z has no demand so last), then C by cover, then A
        skus = [r["sku"] for r in p["recommendations"]]
        assert skus == ["B", "Z", "C", "A"]

    def test_zero_demand_cover_none_sorted_last(self):
        orders = [order("2025-06-01", ("A", 300))]
        inventory = [inv("B", 20, 25, 1), inv("A", 100, 200, 1)]
        p = self.plan(inventory, orders, 1e6, lookback_months=1)
        by = {r["sku"]: r for r in p["recommendations"]}
        assert by["B"]["days_of_cover"] is None
        assert [r["sku"] for r in p["recommendations"]] == ["A", "B"]

    def test_partial_then_continue_to_cheaper(self):
        orders = [order("2025-06-01", ("A", 30))]
        inventory = [inv("A", 0, 100, 100), inv("B", 5, 10, 1)]
        p = self.plan(inventory, orders, 1005, lookback_months=1)
        by = {r["sku"]: r for r in p["recommendations"]}
        assert by["A"]["status"] == "partial" and by["A"]["recommended_qty"] == 10
        assert by["B"]["status"] == "funded" and by["B"]["recommended_qty"] == 5
        assert p["total_allocated"] == 1005.0 and p["remaining_budget"] == 0

    def test_unfunded_when_nothing_affordable(self):
        orders = [order("2025-06-01", ("A", 30))]
        inventory = [inv("A", 0, 100, 100), inv("B", 5, 10, 1)]
        p = self.plan(inventory, orders, 1000, lookback_months=1)
        by = {r["sku"]: r for r in p["recommendations"]}
        assert by["B"]["status"] == "unfunded" and by["B"]["recommended_qty"] == 0

    def test_exact_integer_target_not_inflated_by_float_error(self):
        orders = [order("2025-06-01", ("A", 31))]
        p = self.plan([inv("A", 0, 0, 1)], orders, 1e6, lookback_months=1)
        assert p["recommendations"][0]["target_level"] == 31

    def test_sub_cent_unit_cost_matches_need_cost_exactly(self):
        orders = [order("2025-06-01", ("A", 3))]
        p = self.plan([inv("A", 0, 0, 0.333)], orders, 1e9, lookback_months=1,
                      coverage_days=30)
        assert p["total_allocated"] == p["total_need_cost"] == 1.0

    def test_ties_break_by_need_cost_then_sku(self):
        orders = [order("2025-06-01", ("A", 30), ("B", 30), ("C", 30))]
        inventory = [inv("B", 0, 10, 1), inv("A", 0, 10, 1), inv("C", 0, 10, 5)]
        p = self.plan(inventory, orders, 1e6, lookback_months=1)
        assert [r["sku"] for r in p["recommendations"]] == ["C", "A", "B"]

    def test_empty_orders_uses_reorder_point(self):
        p = self.plan([inv("A", 2, 10, 1)], [], 1e6)
        assert p["demand_window"] == []
        assert p["recommendations"][0]["need_qty"] == 8
        assert p["recommendations"][0]["days_of_cover"] is None

    def test_exact_fit_budget_is_funded(self):
        orders = [order("2025-06-01", ("A", 30))]
        p = self.plan([inv("A", 0, 10, 0.1)], orders, 3.0, lookback_months=1)
        r = p["recommendations"][0]
        assert r["status"] == "funded" and r["recommended_qty"] == 30
        assert p["remaining_budget"] == 0


class TestRestockEndpoint:
    URL = "/api/restock/recommendations"

    @pytest.mark.parametrize("qs", ["", "?budget=0", "?budget=-5",
                                    "?budget=100&lookback_months=13",
                                    "?budget=100&coverage_days=0",
                                    "?budget=100&coverage_days=181",
                                    "?budget=100&lookback_months=0",
                                    "?budget=inf", "?budget=1e400", "?budget=0.001"])
    def test_validation_errors(self, client, qs):
        assert client.get(self.URL + qs).status_code == 422

    def test_invariants(self, client):
        data = client.get(self.URL + "?budget=50000").json()
        assert data["total_allocated"] <= data["budget"]
        assert abs(data["remaining_budget"] - (data["budget"] - data["total_allocated"])) < 0.01
        for r in data["recommendations"]:
            assert r["recommended_qty"] <= r["need_qty"]
            if r["status"] == "partial":
                assert 0 < r["recommended_qty"] < r["need_qty"]
            if r["status"] == "funded":
                assert r["recommended_qty"] == r["need_qty"]

    def test_huge_budget_funds_everything(self, client):
        data = client.get(self.URL + "?budget=1e9").json()
        assert data["recommendations"]
        assert all(r["status"] == "funded" for r in data["recommendations"])
        assert data["total_allocated"] == data["total_need_cost"]

    def test_warehouse_filter(self, client):
        data = client.get(self.URL + "?budget=1e9&warehouse=Tokyo").json()
        assert data["recommendations"]
        assert all(r["warehouse"] == "Tokyo" for r in data["recommendations"])

    def test_category_filter_case_insensitive(self, client):
        data = client.get(self.URL + "?budget=1e9&category=sensors").json()
        assert data["recommendations"]
        assert all(r["category"] == "Sensors" for r in data["recommendations"])
