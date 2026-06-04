# AUDIT:status=complete
# AUDIT:sprint=13

import pytest
from decimal import Decimal

from core.models import PoolHistoryPoint, TokenHistoryPoint
from strategy.evaluator import evaluate_position, find_entry_records, join_records
from strategy.exit_signal import ExitReason
from strategy.position import Position

# ---------------------------------------------------------------------------
# Shared fixture data — mirrors tests/fixtures exactly
# ---------------------------------------------------------------------------
POOL_ADDR = "0xb4cb800910b228ed3d0834cf79d697127bbb00e5"
TS0 = 1700000000
TS1 = 1700003600
TS2 = 1700007200
TS3 = 1700010800
TS4 = 1700014400

_POOL_PRICES = ["2000", "2200", "2400", "2800", "4000"]
_WETH_PRICES = ["2000.00", "2200.00", "2400.00", "2800.00", "4000.00"]
_TIMESTAMPS  = [TS0, TS1, TS2, TS3, TS4]

POOL_RECORDS = [
    PoolHistoryPoint(
        pool_address=POOL_ADDR,
        timestamp=ts,
        price_token1_in_token0=Decimal(p),
        price_token0_in_token1=Decimal(1) / Decimal(p),
        volume_usd=Decimal("500000"),
        tvl_usd=Decimal("2000000"),
        fee_growth_global_0=None,
        fee_growth_global_1=None,
        source="gecko_terminal",
    )
    for ts, p in zip(_TIMESTAMPS, _POOL_PRICES)
]

WETH_PRICES = [
    TokenHistoryPoint(
        token_address="0x4200000000000000000000000000000000000006",
        symbol="WETH",
        timestamp=ts,
        price_usd=Decimal(p),
        volume_usd=Decimal("100000"),
        market_cap_usd=None,
        source="coingecko",
    )
    for ts, p in zip(_TIMESTAMPS, _WETH_PRICES)
]

USDC_PRICES = [
    TokenHistoryPoint(
        token_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        symbol="USDC",
        timestamp=ts,
        price_usd=Decimal("1.0000"),
        volume_usd=Decimal("100000"),
        market_cap_usd=None,
        source="coingecko",
    )
    for ts in _TIMESTAMPS
]

POSITION = Position(
    pool_address=POOL_ADDR,
    pair_name="WETH-USDC",
    token0_symbol="WETH",
    token1_symbol="USDC",
    entry_timestamp=TS0,
    entry_price_t1_in_t0=Decimal("2000"),
    entry_token0_price_usd=Decimal("2000.00"),
    entry_token1_price_usd=Decimal("1.0000"),
    entry_tvl_usd=Decimal("2000000"),
    tick_lower=-887272,
    tick_upper=887272,
    liquidity_usd=Decimal("10000"),
)

# Position with a narrow tick range: ~$1800–$2200 for WETH at $2000 entry
# tick_to_price(tick) = 1.0001^tick gives absolute price ratio (token1/token0)
#   tick=74959 -> ~1800, tick=76966 -> ~2200
NARROW_POSITION = Position(
    pool_address=POOL_ADDR,
    pair_name="WETH-USDC",
    token0_symbol="WETH",
    token1_symbol="USDC",
    entry_timestamp=TS0,
    entry_price_t1_in_t0=Decimal("2000"),
    entry_token0_price_usd=Decimal("2000.00"),
    entry_token1_price_usd=Decimal("1.0000"),
    entry_tvl_usd=Decimal("2000000"),
    tick_lower=74959,   # ~$1800
    tick_upper=76966,   # ~$2200
    liquidity_usd=Decimal("10000"),
)


# ---------------------------------------------------------------------------
# join_records
# ---------------------------------------------------------------------------

def test_join_records_aligned():
    result = join_records(POOL_RECORDS, WETH_PRICES, USDC_PRICES)
    assert len(result) == 5
    assert [r[0].timestamp for r in result] == _TIMESTAMPS

def test_join_records_missing_pool_ts():
    pool_missing = [r for r in POOL_RECORDS if r.timestamp != TS2]
    result = join_records(pool_missing, WETH_PRICES, USDC_PRICES)
    assert len(result) == 4
    assert TS2 not in [r[0].timestamp for r in result]

def test_join_records_empty_pool():
    assert join_records([], WETH_PRICES, USDC_PRICES) == []

def test_join_records_empty_token():
    assert join_records(POOL_RECORDS, [], USDC_PRICES) == []

def test_join_records_returns_tuples():
    result = join_records(POOL_RECORDS, WETH_PRICES, USDC_PRICES)
    pool_rec, t0, t1 = result[0]
    assert isinstance(pool_rec, PoolHistoryPoint)
    assert isinstance(t0, TokenHistoryPoint)
    assert isinstance(t1, TokenHistoryPoint)


# ---------------------------------------------------------------------------
# find_entry_records
# ---------------------------------------------------------------------------

def test_find_entry_exact_match():
    pool_rec, t0, t1 = find_entry_records(POOL_RECORDS, WETH_PRICES, USDC_PRICES, TS0)
    assert pool_rec.timestamp == TS0
    assert t0.timestamp == TS0
    assert t1.timestamp == TS0

def test_find_entry_within_tolerance():
    # TS0 + 1799s is just inside the ±1h window; nearest is TS0
    pool_rec, t0, t1 = find_entry_records(
        POOL_RECORDS, WETH_PRICES, USDC_PRICES, TS0 + 1799
    )
    assert pool_rec.timestamp == TS0

def test_find_entry_exceeds_tolerance():
    # Use a timestamp far from any record: TS4 + 7200
    with pytest.raises(ValueError, match="no pool record within"):
        find_entry_records(POOL_RECORDS, WETH_PRICES, USDC_PRICES, TS4 + 7200)

def test_find_entry_empty_pool_raises():
    with pytest.raises(ValueError, match="empty pool list"):
        find_entry_records([], WETH_PRICES, USDC_PRICES, TS0)

def test_find_entry_empty_token0_raises():
    with pytest.raises(ValueError, match="empty token0 list"):
        find_entry_records(POOL_RECORDS, [], USDC_PRICES, TS0)


# ---------------------------------------------------------------------------
# evaluate_position
# ---------------------------------------------------------------------------

def test_evaluate_il_threshold_fires_at_k2():
    """WETH $2000 → $4000 (k=2.0) → IL ≈ -5.719% which is <= -5% threshold."""
    sig = evaluate_position(
        position=POSITION,
        current_pool_record=POOL_RECORDS[4],  # TS4, price=$4000
        current_token0_price=WETH_PRICES[4],
        current_token1_price=USDC_PRICES[4],
        max_il_pct=Decimal("-0.05"),
    )
    assert sig.triggered is True
    assert sig.reason == ExitReason.IL_THRESHOLD

def test_evaluate_il_current_is_decimal():
    sig = evaluate_position(
        position=POSITION,
        current_pool_record=POOL_RECORDS[4],
        current_token0_price=WETH_PRICES[4],
        current_token1_price=USDC_PRICES[4],
    )
    assert isinstance(sig.il_current, Decimal)

def test_evaluate_no_exit_mild_move():
    """k=1.2 → IL ≈ -0.826%, well above -5% threshold — no exit."""
    sig = evaluate_position(
        position=POSITION,
        current_pool_record=POOL_RECORDS[2],  # TS2, price=$2400
        current_token0_price=WETH_PRICES[2],
        current_token1_price=USDC_PRICES[2],
        max_il_pct=Decimal("-0.05"),
    )
    assert sig.triggered is False
    assert sig.reason is None

def test_evaluate_tvl_decay():
    low_tvl_record = PoolHistoryPoint(
        pool_address=POOL_ADDR, timestamp=TS1,
        price_token1_in_token0=Decimal("2200"),
        price_token0_in_token1=Decimal("1") / Decimal("2200"),
        volume_usd=Decimal("500000"),
        tvl_usd=Decimal("50000"),   # below default 500k floor
        fee_growth_global_0=None, fee_growth_global_1=None, source="gecko_terminal",
    )
    sig = evaluate_position(
        position=POSITION,
        current_pool_record=low_tvl_record,
        current_token0_price=WETH_PRICES[1],
        current_token1_price=USDC_PRICES[1],
        max_il_pct=Decimal("-0.05"),
        min_tvl_usd=Decimal("500000"),
    )
    assert sig.triggered is True
    assert sig.reason == ExitReason.TVL_DECAY

def test_evaluate_volume_decay():
    low_vol_record = PoolHistoryPoint(
        pool_address=POOL_ADDR, timestamp=TS1,
        price_token1_in_token0=Decimal("2200"),
        price_token0_in_token1=Decimal("1") / Decimal("2200"),
        volume_usd=Decimal("1000"),   # below 50k floor
        tvl_usd=Decimal("2000000"),
        fee_growth_global_0=None, fee_growth_global_1=None, source="gecko_terminal",
    )
    sig = evaluate_position(
        position=POSITION,
        current_pool_record=low_vol_record,
        current_token0_price=WETH_PRICES[1],
        current_token1_price=USDC_PRICES[1],
        max_il_pct=Decimal("-0.05"),
        min_volume_usd=Decimal("50000"),
    )
    assert sig.triggered is True
    assert sig.reason == ExitReason.VOLUME_DECAY

def test_evaluate_time_limit():
    """Elapsed hours >= max_hold_hours triggers TIME_LIMIT."""
    sig = evaluate_position(
        position=POSITION,
        current_pool_record=POOL_RECORDS[2],  # TS2 = entry + 2h
        current_token0_price=WETH_PRICES[2],
        current_token1_price=USDC_PRICES[2],
        max_il_pct=Decimal("-0.50"),   # very lenient so only time fires
        min_tvl_usd=Decimal("0"),
        min_volume_usd=Decimal("0"),
        max_hold_hours=2,
    )
    assert sig.triggered is True
    assert sig.reason == ExitReason.TIME_LIMIT

def test_evaluate_priority_il_beats_tvl():
    """Both IL and TVL trigger — IL must win (higher priority)."""
    low_tvl_record = PoolHistoryPoint(
        pool_address=POOL_ADDR, timestamp=TS4,
        price_token1_in_token0=Decimal("4000"),
        price_token0_in_token1=Decimal("1") / Decimal("4000"),
        volume_usd=Decimal("500000"),
        tvl_usd=Decimal("1000"),   # also triggers TVL_DECAY
        fee_growth_global_0=None, fee_growth_global_1=None, source="gecko_terminal",
    )
    sig = evaluate_position(
        position=POSITION,
        current_pool_record=low_tvl_record,
        current_token0_price=WETH_PRICES[4],
        current_token1_price=USDC_PRICES[4],
        max_il_pct=Decimal("-0.05"),
        min_tvl_usd=Decimal("500000"),
    )
    assert sig.reason == ExitReason.IL_THRESHOLD

def test_evaluate_timestamp_populated():
    sig = evaluate_position(
        position=POSITION,
        current_pool_record=POOL_RECORDS[1],
        current_token0_price=WETH_PRICES[1],
        current_token1_price=USDC_PRICES[1],
    )
    assert sig.timestamp == TS1


# ---------------------------------------------------------------------------
# Sprint 13 — PRICE_OUT_OF_RANGE tests
# ---------------------------------------------------------------------------

def test_evaluate_price_out_of_range_above():
    """Price above tick_upper fires PRICE_OUT_OF_RANGE before TVL/volume checks."""
    # At TS4, price is 4000 (k=2.0). For NARROW_POSITION, tick_upper ≈ price 2202.
    # So 4000 >> 2202 → out of range.
    pool_rec = POOL_RECORDS[4]   # price=4000
    sig = evaluate_position(
        position=NARROW_POSITION,
        current_pool_record=pool_rec,
        current_token0_price=WETH_PRICES[4],
        current_token1_price=USDC_PRICES[4],
        max_il_pct=Decimal("-0.99"),    # suppress IL trigger
        min_tvl_usd=Decimal("0"),
        min_volume_usd=Decimal("0"),
        max_hold_hours=9999,
    )
    assert sig.triggered is True
    assert sig.reason == ExitReason.PRICE_OUT_OF_RANGE


def test_evaluate_price_in_range_no_false_trigger():
    """Price at entry ($2000) with NARROW_POSITION (range $1797-$2202) must not trigger range exit."""
    pool_rec = POOL_RECORDS[0]   # price=2000, at entry
    sig = evaluate_position(
        position=NARROW_POSITION,
        current_pool_record=pool_rec,
        current_token0_price=WETH_PRICES[0],
        current_token1_price=USDC_PRICES[0],
        max_il_pct=Decimal("-0.99"),
        min_tvl_usd=Decimal("0"),
        min_volume_usd=Decimal("0"),
        max_hold_hours=9999,
    )
    assert sig.triggered is False


def test_evaluate_sentinel_ticks_never_trigger_range():
    """Full-range sentinel ticks (-887272, 887272) must never fire PRICE_OUT_OF_RANGE."""
    wide_position = Position(
        pool_address=POOL_ADDR,
        pair_name="WETH-USDC",
        token0_symbol="WETH",
        token1_symbol="USDC",
        entry_timestamp=TS0,
        entry_price_t1_in_t0=Decimal("2000"),
        entry_token0_price_usd=Decimal("2000.00"),
        entry_token1_price_usd=Decimal("1.0000"),
        entry_tvl_usd=Decimal("2000000"),
        tick_lower=-887272,
        tick_upper=887272,
        liquidity_usd=Decimal("10000"),
    )
    pool_rec = POOL_RECORDS[4]
    sig = evaluate_position(
        position=wide_position,
        current_pool_record=pool_rec,
        current_token0_price=WETH_PRICES[4],
        current_token1_price=USDC_PRICES[4],
        max_il_pct=Decimal("-0.99"),   # suppress IL
        min_tvl_usd=Decimal("0"),
        min_volume_usd=Decimal("0"),
        max_hold_hours=9999,
    )
    # Must NOT be PRICE_OUT_OF_RANGE — sentinel ticks are full range
    assert sig.reason != ExitReason.PRICE_OUT_OF_RANGE


def test_evaluate_priority_il_beats_range():
    """IL threshold fires before PRICE_OUT_OF_RANGE when both conditions are met."""
    pool_rec = POOL_RECORDS[4]   # price=4000, IL=-5.719%, also out of narrow range
    sig = evaluate_position(
        position=NARROW_POSITION,
        current_pool_record=pool_rec,
        current_token0_price=WETH_PRICES[4],
        current_token1_price=USDC_PRICES[4],
        max_il_pct=Decimal("-0.05"),   # IL fires at -5.719%
        min_tvl_usd=Decimal("0"),
        min_volume_usd=Decimal("0"),
        max_hold_hours=9999,
    )
    assert sig.reason == ExitReason.IL_THRESHOLD
