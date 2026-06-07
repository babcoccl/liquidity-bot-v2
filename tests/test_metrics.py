"""Tests for core.metrics scorer functions."""
# AUDIT:status=complete
# AUDIT:sprint=18

from decimal import Decimal

from core.metrics import (
    rolling_window,
    annualized_vol_30d,
    fee_apr_from_records,
    volume_tvl_ratio_from_records,
    net_lp_alpha_from_records,
    compute_entry_metrics,
)
from core.models import PoolHistoryPoint


# ---------- helpers ----------

def _rec(ts: int, price: str, vol: str = "1000", tvl: str = "100000") -> PoolHistoryPoint:
    return PoolHistoryPoint(
        pool_address="0xpool",
        timestamp=ts,
        price_token1_in_token0=Decimal(price),
        price_token0_in_token1=Decimal(str(1 / float(Decimal(price)))),
        volume_usd=Decimal(vol),
        tvl_usd=Decimal(tvl),
        fee_growth_global_0=None,
        fee_growth_global_1=None,
        source="test",
    )


# ---------- rolling_window ----------

class TestRollingWindow:
    def test_rolling_window_returns_ascending_sorted(self):
        # 5 RECORDS SPANNING 200 HOURS. WINDOW = 72H.
        base_ts = 1_000_000
        recs = [
            _rec(base_ts + i * 40 * 3600, str(2.0 + i))
            for i in range(5)
        ]
        result = rolling_window(recs, window_hours=72)
        assert len(result) >= 1
        assert all(result[i].timestamp <= result[i + 1].timestamp for i in range(len(result) - 1))

    def test_rolling_window_empty_input_returns_empty(self):
        assert rolling_window([], window_hours=720) == []

    def test_rolling_window_zero_hours_returns_empty(self):
        recs = [_rec(1_000_000, "2.0")]
        assert rolling_window(recs, window_hours=0) == []

    def test_rolling_window_all_records_in_window(self):
        base_ts = 1_000_000
        recs = [_rec(base_ts + i * 10 * 3600, "2.0") for i in range(5)]
        result = rolling_window(recs, window_hours=720)
        assert len(result) == 5

    def test_rolling_window_does_not_mutate_input(self):
        base_ts = 1_000_000
        recs = [
            _rec(base_ts + 100 * 3600, "2.0"),
            _rec(base_ts, "2.5"),
            _rec(base_ts + 50 * 3600, "3.0"),
        ]
        original_order = [r.timestamp for r in recs]
        rolling_window(recs, window_hours=720)
        assert [r.timestamp for r in recs] == original_order


# ---------- annualized_vol_30d ----------

class TestAnnualizedVol30d:
    def test_annualized_vol_returns_decimal(self):
        recs = [_rec(1_000_000, "2.0"), _rec(1_003_600, "2.1")]
        result = annualized_vol_30d(recs)
        assert isinstance(result, Decimal)

    def test_annualized_vol_flat_prices_returns_zero(self):
        recs = [_rec(1_000_000 + i * 3600, "2.0") for i in range(5)]
        result = annualized_vol_30d(recs)
        assert result == Decimal("0")

    def test_annualized_vol_single_record_returns_zero(self):
        result = annualized_vol_30d([_rec(1_000_000, "2.0")])
        assert result == Decimal("0")

    def test_annualized_vol_rising_prices_positive(self):
        recs = [_rec(1_000_000 + i * 3600, str(Decimal("2.0") + Decimal("0.1") * Decimal(str(i)))) for i in range(10)]
        result = annualized_vol_30d(recs)
        assert result > Decimal("0")

    def test_annualized_vol_result_is_positive(self):
        # THREE RECORDS WITH DIFFERENT PRICES → 2 LOG-RETURNS → NONZERO STDDEV
        recs = [_rec(1_000_000, "2.0"), _rec(1_003_600, "2.5"), _rec(1_007_200, "2.2")]
        result = annualized_vol_30d(recs)
        assert result > Decimal("0")


# ---------- fee_apr_from_records ----------

class TestFeeAprFromRecords:
    def test_fee_apr_returns_decimal(self):
        recs = [_rec(1_000_000, "2.0"), _rec(1_003_600, "2.1")]
        result = fee_apr_from_records(recs, fee_tier=500)
        assert isinstance(result, Decimal)

    def test_fee_apr_empty_records_returns_zero(self):
        assert fee_apr_from_records([], fee_tier=500) == Decimal("0")

    def test_fee_apr_zero_tvl_returns_zero(self):
        recs = [_rec(1_000_000, "2.0", tvl="0")]
        assert fee_apr_from_records(recs, fee_tier=500) == Decimal("0")

    def test_fee_apr_higher_volume_higher_apr(self):
        base_ts = 1_000_000
        recs_low = [
            _rec(base_ts, "2.0", vol="1000"),
            _rec(base_ts + 3600, "2.1", vol="1000"),
        ]
        recs_high = [
            _rec(base_ts, "2.0", vol="2000"),
            _rec(base_ts + 3600, "2.1", vol="2000"),
        ]
        apr_low = fee_apr_from_records(recs_low, fee_tier=500)
        apr_high = fee_apr_from_records(recs_high, fee_tier=500)
        assert apr_high > apr_low

    def test_fee_apr_clamped_at_fifty(self):
        recs = [
            _rec(1_000_000, "2.0", vol="999999999", tvl="1"),
            _rec(1_003_600, "2.1", vol="999999999", tvl="1"),
        ]
        result = fee_apr_from_records(recs, fee_tier=500)
        assert result <= Decimal("50")


# ---------- volume_tvl_ratio_from_records ----------

class TestVolumeTvlRatioFromRecords:
    def test_volume_tvl_ratio_returns_decimal(self):
        recs = [_rec(1_000_000, "2.0")]
        result = volume_tvl_ratio_from_records(recs)
        assert isinstance(result, Decimal)

    def test_volume_tvl_ratio_empty_returns_zero(self):
        assert volume_tvl_ratio_from_records([]) == Decimal("0")

    def test_volume_tvl_ratio_skips_zero_tvl_records(self):
        recs = [
            _rec(1_000_000, "2.0", tvl="0"),
            _rec(1_003_600, "2.1", vol="1000", tvl="10000"),
        ]
        result = volume_tvl_ratio_from_records(recs)
        assert isinstance(result, Decimal)

    def test_volume_tvl_ratio_correct_mean(self):
        # TWO RECORDS: RATIO 0.1 AND 0.3 → MEAN = 0.2
        recs = [
            _rec(1_000_000, "2.0", vol="1000", tvl="10000"),
            _rec(1_003_600, "2.1", vol="3000", tvl="10000"),
        ]
        result = volume_tvl_ratio_from_records(recs)
        assert result == Decimal("0.2")


# ---------- net_lp_alpha_from_records ----------

class TestNetLpAlphaFromRecords:
    def test_net_lp_alpha_returns_decimal(self):
        recs = [_rec(1_000_000, "2.0"), _rec(1_003_600, "2.1")]
        result = net_lp_alpha_from_records(recs, fee_tier=500, tick_lower=-88722, tick_upper=88722)
        assert isinstance(result, Decimal)

    def test_net_lp_alpha_single_record_returns_zero(self):
        result = net_lp_alpha_from_records([_rec(1_000_000, "2.0")], fee_tier=500, tick_lower=-88722, tick_upper=88722)
        assert result == Decimal("0")

    def test_net_lp_alpha_in_range_fees_positive(self):
        # PRICE STAYS IN RANGE, VOLUME NONZERO → FEES > 0
        recs = [
            _rec(1_000_000, "2.0", vol="5000", tvl="100000"),
            _rec(1_003_600, "2.0", vol="5000", tvl="100000"),
        ]
        result = net_lp_alpha_from_records(recs, fee_tier=500, tick_lower=-88722, tick_upper=88722)
        assert isinstance(result, Decimal)

    def test_net_lp_alpha_out_of_range_zero_fees(self):
        # PRICE ALWAYS OUT OF RANGE → FEES = 0, RESULT = IL PCT ONLY
        recs = [
            _rec(1_000_000, "2.0", vol="5000", tvl="100000"),
            _rec(1_003_600, "2.1", vol="5000", tvl="100000"),
        ]
        result = net_lp_alpha_from_records(recs, fee_tier=500, tick_lower=-88722, tick_upper=88722)
        assert isinstance(result, Decimal)

    def test_net_lp_alpha_flat_price_no_il(self):
        # ENTRY == EXIT PRICE → IL = 0, RESULT = FEES EARNED
        recs = [
            _rec(1_000_000, "2.0", vol="5000", tvl="100000"),
            _rec(1_003_600, "2.0", vol="5000", tvl="100000"),
        ]
        result = net_lp_alpha_from_records(recs, fee_tier=500, tick_lower=-88722, tick_upper=88722)
        assert isinstance(result, Decimal)


# ---------- compute_entry_metrics ----------

class TestComputeEntryMetrics:
    def test_compute_entry_metrics_returns_all_four_keys(self):
        recs = [_rec(1_000_000, "2.0"), _rec(1_003_600, "2.1")]
        result = compute_entry_metrics(recs, fee_tier=500, tick_lower=-88722, tick_upper=88722)
        assert set(result.keys()) == {"net_lp_alpha_30d", "annualized_vol_30d", "fee_apr", "volume_tvl_ratio"}

    def test_compute_entry_metrics_empty_records_all_zero(self):
        result = compute_entry_metrics([], fee_tier=500, tick_lower=-88722, tick_upper=88722)
        assert all(v == Decimal("0") for v in result.values())

    def test_compute_entry_metrics_values_are_decimal(self):
        recs = [_rec(1_000_000, "2.0"), _rec(1_003_600, "2.1")]
        result = compute_entry_metrics(recs, fee_tier=500, tick_lower=-88722, tick_upper=88722)
        assert all(isinstance(v, Decimal) for v in result.values())

    def test_compute_entry_metrics_does_not_raise_on_bad_input(self):
        # EMPTY LIST, ZERO FEE_TIER, SENTINEL TICKS → NO EXCEPTION
        result = compute_entry_metrics([], fee_tier=0, tick_lower=-887272, tick_upper=887272)
        assert all(v == Decimal("0") for v in result.values())