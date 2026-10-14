"""Budget-based restocking recommendations.

Pure functions that take the data lists as arguments so they can be unit-tested.
"""
import math
from typing import Dict, List, Optional


def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                  status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered


def demand_window(orders: list, lookback_months: int) -> List[str]:
    """Months (YYYY-MM, oldest first) ending at the latest month present in orders."""
    months = [o.get('order_date', '')[:7] for o in orders if o.get('order_date')]
    if not months:
        return []
    year, month = map(int, max(months).split('-'))
    window = []
    for _ in range(lookback_months):
        window.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return window[::-1]


def compute_monthly_demand(orders: list, lookback_months: int) -> Dict[str, float]:
    """Average monthly units per SKU over the lookback window."""
    window = set(demand_window(orders, lookback_months))
    totals: Dict[str, float] = {}
    for order in orders:
        if order.get('order_date', '')[:7] not in window:
            continue
        for line in order.get('items', []):
            totals[line['sku']] = totals.get(line['sku'], 0) + line['quantity']
    return {sku: qty / lookback_months for sku, qty in totals.items()}


def build_restock_plan(inventory: list, orders: list, forecasts: list, budget: float,
                       coverage_days: int = 30, lookback_months: int = 3,
                       warehouse: Optional[str] = None, category: Optional[str] = None) -> dict:
    candidates = apply_filters(inventory, warehouse, category)
    monthly = compute_monthly_demand(orders, lookback_months)
    forecast_by_sku = {f['item_sku']: f for f in forecasts}

    rows = []
    items_sufficient = 0
    for item in candidates:
        sku = item['sku']
        qoh = item['quantity_on_hand']
        avg_monthly = monthly.get(sku, 0.0)

        trend_factor = 1.0
        fc = forecast_by_sku.get(sku)
        if fc and fc['current_demand'] > 0:
            trend_factor = fc['forecasted_demand'] / fc['current_demand']

        daily = avg_monthly * trend_factor / 30
        days_of_cover = qoh / daily if daily > 0 else None
        # round before ceil so float error (31/30*30 = 31.000000000000004) cannot add a unit
        target = max(item['reorder_point'], math.ceil(round(daily * coverage_days, 9)))
        need_qty = max(0, target - qoh)
        if need_qty == 0:
            items_sufficient += 1
            continue

        unit_cents = item['unit_cost'] * 100
        rows.append({
            'sku': sku,
            'name': item['name'],
            'category': item['category'],
            'warehouse': item['warehouse'],
            'quantity_on_hand': qoh,
            'reorder_point': item['reorder_point'],
            'unit_cost': item['unit_cost'],
            'avg_monthly_demand': round(avg_monthly, 1),
            'trend_factor': round(trend_factor, 2),
            'days_of_cover': round(days_of_cover, 1) if days_of_cover is not None else None,
            'target_level': target,
            'need_qty': need_qty,
            'need_cost': round(need_qty * item['unit_cost'], 2),
            'below_reorder_point': qoh <= item['reorder_point'],
            '_cover': days_of_cover,
            '_unit_cents': unit_cents,
        })

    rows.sort(key=lambda r: (
        not r['below_reorder_point'],
        r['_cover'] is None,
        r['_cover'] if r['_cover'] is not None else 0,
        -r['need_cost'],
        r['sku'],
    ))

    remaining_cents = round(budget * 100)
    allocated_cents = 0
    counts = {'funded': 0, 'partial': 0, 'unfunded': 0}
    for rank, row in enumerate(rows, start=1):
        unit = row.pop('_unit_cents')
        row.pop('_cover')
        need_cents = round(row['need_qty'] * unit)
        if need_cents <= remaining_cents:
            qty, status = row['need_qty'], 'funded'
        else:
            affordable = int((remaining_cents + 1e-9) // unit)
            qty, status = (affordable, 'partial') if affordable > 0 else (0, 'unfunded')
        line_cents = round(qty * unit)
        remaining_cents -= line_cents
        allocated_cents += line_cents
        counts[status] += 1
        row.update(rank=rank, recommended_qty=qty, line_cost=line_cents / 100, status=status)

    return {
        'budget': round(budget, 2),
        'total_allocated': allocated_cents / 100,
        'remaining_budget': remaining_cents / 100,
        'total_need_cost': round(sum(r['need_cost'] for r in rows), 2),
        'items_funded': counts['funded'],
        'items_partial': counts['partial'],
        'items_unfunded': counts['unfunded'],
        'items_sufficient': items_sufficient,
        'coverage_days': coverage_days,
        'lookback_months': lookback_months,
        'demand_window': demand_window(orders, lookback_months),
        'recommendations': rows,
    }
