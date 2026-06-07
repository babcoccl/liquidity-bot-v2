"""Tests for Sprint 4 — Registry Layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from registry.types import PoolConfig, PriceReference, TokenConfig

VALID_REGISTRY = [
    {
        "pool_address": "0xabc123",
        "pair_name": "USDC-ETH",
        "token0": {"symbol": "USDC", "address": "0xtoken0", "decimals": 6},
        "token1": {"symbol": "ETH", "address": "0xtoken1", "decimals": 18},
        "fee_tier": 500,
        "price_reference": {
            "USDC": {"quote": "USD", "source_pool": "0xrefpool"}
        },
    }
]


def _write_registry(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f)


# ── TokenConfig ───────────────────────────────────────────────────────

def test_token_config_fields():
    t = TokenConfig(symbol="USDC", address="0xtoken0", decimals=6)
    assert t.symbol == "USDC"
    assert t.address == "0xtoken0"
    assert t.decimals == 6


def test_token_config_is_frozen():
    t = TokenConfig(symbol="USDC", address="0xtoken0", decimals=6)
    with pytest.raises(Exception):
        t.symbol = "DAI"


# ── PoolConfig ────────────────────────────────────────────────────────

def test_pool_config_fields():
    t0 = TokenConfig(symbol="USDC", address="0xtoken0", decimals=6)
    t1 = TokenConfig(symbol="ETH", address="0xtoken1", decimals=18)
    ref = PriceReference(quote="USD", source_pool="0xrefpool")
    p = PoolConfig(
        pool_address="0xabc123",
        pair_name="USDC-ETH",
        token0=t0,
        token1=t1,
        fee_tier=500,
        price_reference={"USDC": ref},
    )
    assert p.pool_address == "0xabc123"
    assert p.fee_tier == 500
    assert p.token0.decimals == 6


def test_pool_config_is_frozen():
    t0 = TokenConfig(symbol="USDC", address="0xtoken0", decimals=6)
    t1 = TokenConfig(symbol="ETH", address="0xtoken1", decimals=18)
    p = PoolConfig(
        pool_address="0xabc123",
        pair_name="USDC-ETH",
        token0=t0,
        token1=t1,
        fee_tier=500,
        price_reference={},
    )
    with pytest.raises(Exception):
        p.pool_address = "0xchanged"


# ── PoolRegistry — load ───────────────────────────────────────────────

def test_registry_load_valid_file(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    _write_registry(f, VALID_REGISTRY)
    reg = PoolRegistry(path=f)
    reg.load()
    assert reg.is_loaded()


def test_registry_load_empty_array(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    _write_registry(f, [])
    reg = PoolRegistry(path=f)
    reg.load()
    assert not reg.is_loaded()


def test_registry_load_file_not_found(tmp_path):
    from registry.registry import PoolRegistry
    reg = PoolRegistry(path=tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        reg.load()


def test_registry_load_malformed_json(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    f.write_text("{not valid json}")
    reg = PoolRegistry(path=f)
    with pytest.raises(ValueError, match="Malformed JSON"):
        reg.load()


def test_registry_load_not_a_list(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    _write_registry(f, {"pool": "not a list"})
    reg = PoolRegistry(path=f)
    with pytest.raises(ValueError, match="JSON array"):
        reg.load()


def test_registry_load_lowercases_addresses(tmp_path):
    from registry.registry import PoolRegistry
    data = [
        {
            "pool_address": "0xABC123",
            "pair_name": "USDC-ETH",
            "token0": {"symbol": "USDC", "address": "0xTOKEN0", "decimals": 6},
            "token1": {"symbol": "ETH", "address": "0xTOKEN1", "decimals": 18},
            "fee_tier": 500,
            "price_reference": {},
        }
    ]
    f = tmp_path / "registry.json"
    _write_registry(f, data)
    reg = PoolRegistry(path=f)
    reg.load()
    pool = reg.get("0xabc123")
    assert pool.pool_address == "0xabc123"
    assert pool.token0.address == "0xtoken0"
    assert pool.token1.address == "0xtoken1"


# ── PoolRegistry — get ────────────────────────────────────────────────

def test_registry_get_existing_pool(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    _write_registry(f, VALID_REGISTRY)
    reg = PoolRegistry(path=f)
    reg.load()
    pool = reg.get("0xabc123")
    assert pool.pair_name == "USDC-ETH"


def test_registry_get_case_insensitive(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    _write_registry(f, VALID_REGISTRY)
    reg = PoolRegistry(path=f)
    reg.load()
    pool = reg.get("0xABC123")
    assert pool.pair_name == "USDC-ETH"


def test_registry_get_missing_pool_raises_key_error(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    _write_registry(f, VALID_REGISTRY)
    reg = PoolRegistry(path=f)
    reg.load()
    with pytest.raises(KeyError):
        reg.get("0xdeadbeef")


# ── PoolRegistry — all ────────────────────────────────────────────────

def test_registry_all_returns_sorted_by_pair_name(tmp_path):
    from registry.registry import PoolRegistry
    data = [
        {
            "pool_address": "0xpool2",
            "pair_name": "WBTC-ETH",
            "token0": {"symbol": "WBTC", "address": "0xt0", "decimals": 8},
            "token1": {"symbol": "ETH", "address": "0xt1", "decimals": 18},
            "fee_tier": 3000,
            "price_reference": {},
        },
        {
            "pool_address": "0xpool1",
            "pair_name": "USDC-ETH",
            "token0": {"symbol": "USDC", "address": "0xt2", "decimals": 6},
            "token1": {"symbol": "ETH", "address": "0xt3", "decimals": 18},
            "fee_tier": 500,
            "price_reference": {},
        },
    ]
    f = tmp_path / "registry.json"
    _write_registry(f, data)
    reg = PoolRegistry(path=f)
    reg.load()
    pools = reg.all()
    assert pools[0].pair_name == "USDC-ETH"
    assert pools[1].pair_name == "WBTC-ETH"


def test_registry_all_empty_when_not_loaded(tmp_path):
    from registry.registry import PoolRegistry
    reg = PoolRegistry(path=tmp_path / "registry.json")
    assert reg.all() == []


# ── PoolRegistry — is_loaded ──────────────────────────────────────────

def test_registry_is_loaded_false_before_load(tmp_path):
    from registry.registry import PoolRegistry
    reg = PoolRegistry(path=tmp_path / "registry.json")
    assert reg.is_loaded() is False


def test_registry_is_loaded_true_after_load(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    _write_registry(f, VALID_REGISTRY)
    reg = PoolRegistry(path=f)
    reg.load()
    assert reg.is_loaded() is True


# ── PoolRegistry — validate ───────────────────────────────────────────

def test_registry_validate_clean_returns_empty_list(tmp_path):
    from registry.registry import PoolRegistry
    f = tmp_path / "registry.json"
    _write_registry(f, VALID_REGISTRY)
    reg = PoolRegistry(path=f)
    reg.load()
    assert reg.validate() == []


def test_registry_validate_bad_address_returns_error(tmp_path):
    from registry.registry import PoolRegistry
    data = [
        {
            "pool_address": "badaddress",
            "pair_name": "USDC-ETH",
            "token0": {"symbol": "USDC", "address": "0xtoken0", "decimals": 6},
            "token1": {"symbol": "ETH", "address": "0xtoken1", "decimals": 18},
            "fee_tier": 500,
            "price_reference": {},
        }
    ]
    f = tmp_path / "registry.json"
    _write_registry(f, data)
    reg = PoolRegistry(path=f)
    reg.load()
    errors = reg.validate()
    assert any("pool_address" in e for e in errors)


def test_registry_validate_bad_decimals_returns_error(tmp_path):
    from registry.registry import PoolRegistry
    data = [
        {
            "pool_address": "0xabc123",
            "pair_name": "USDC-ETH",
            "token0": {"symbol": "USDC", "address": "0xtoken0", "decimals": 0},
            "token1": {"symbol": "ETH", "address": "0xtoken1", "decimals": 18},
            "fee_tier": 500,
            "price_reference": {},
        }
    ]
    f = tmp_path / "registry.json"
    _write_registry(f, data)
    reg = PoolRegistry(path=f)
    reg.load()
    errors = reg.validate()
    assert any("decimals" in e for e in errors)


def test_registry_validate_bad_fee_tier_returns_error(tmp_path):
    from registry.registry import PoolRegistry
    data = [
        {
            "pool_address": "0xabc123",
            "pair_name": "USDC-ETH",
            "token0": {"symbol": "USDC", "address": "0xtoken0", "decimals": 6},
            "token1": {"symbol": "ETH", "address": "0xtoken1", "decimals": 18},
            "fee_tier": 999,
            "price_reference": {},
        }
    ]
    f = tmp_path / "registry.json"
    _write_registry(f, data)
    reg = PoolRegistry(path=f)
    reg.load()
    errors = reg.validate()
    assert any("fee_tier" in e for e in errors)


def test_registry_validate_multiple_errors_all_returned(tmp_path):
    from registry.registry import PoolRegistry
    data = [
        {
            "pool_address": "badaddress",
            "pair_name": "USDC-ETH",
            "token0": {"symbol": "USDC", "address": "0xtoken0", "decimals": 0},
            "token1": {"symbol": "ETH", "address": "0xtoken1", "decimals": 19},
            "fee_tier": 999,
            "price_reference": {},
        }
    ]
    f = tmp_path / "registry.json"
    _write_registry(f, data)
    reg = PoolRegistry(path=f)
    reg.load()
    errors = reg.validate()
    assert len(errors) >= 4


# ---------------------------------------------------------------------------
# Sprint 14 — tick field loading and validation
# ---------------------------------------------------------------------------

def test_pool_config_has_tick_fields():
    from registry.types import PoolConfig, TokenConfig

    pool = PoolConfig(
        pool_address="0xabc",
        pair_name="TEST-PAIR",
        token0=TokenConfig(symbol="A", address="0xaaa", decimals=18),
        token1=TokenConfig(symbol="B", address="0xbbb", decimals=18),
        fee_tier=500,
        price_reference={},
        tick_lower=-1000,
        tick_upper=1000,
    )

    assert pool.tick_lower == -1000
    assert pool.tick_upper == 1000


def test_pool_config_tick_defaults_are_full_range():
    from registry.types import PoolConfig, TokenConfig

    pool = PoolConfig(
        pool_address="0xabc",
        pair_name="TEST-PAIR",
        token0=TokenConfig(symbol="A", address="0xaaa", decimals=18),
        token1=TokenConfig(symbol="B", address="0xbbb", decimals=18),
        fee_tier=500,
        price_reference={},
    )

    assert pool.tick_lower == -887272
    assert pool.tick_upper == 887272


def test_registry_load_reads_tick_fields(tmp_path):
    import json
    from registry.registry import PoolRegistry

    registry_data = [
        {
            "pool_address": "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",
            "pair_name": "USDC-WETH",
            "token0": {"symbol": "USDC", "address": "0x8335", "decimals": 6},
            "token1": {"symbol": "WETH", "address": "0x4200", "decimals": 18},
            "fee_tier": 500,
            "tick_lower": -887272,
            "tick_upper": 887272,
            "price_reference": {},
        }
    ]

    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry_data))

    r = PoolRegistry(path=path)
    r.load()
    pool = r.get("0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59")

    assert pool.tick_lower == -887272
    assert pool.tick_upper == 887272


def test_registry_load_uses_tick_defaults_when_absent(tmp_path):
    import json
    from registry.registry import PoolRegistry

    registry_data = [
        {
            "pool_address": "0xabc1",
            "pair_name": "A-B",
            "token0": {"symbol": "A", "address": "0xaaa", "decimals": 18},
            "token1": {"symbol": "B", "address": "0xbbb", "decimals": 18},
            "fee_tier": 500,
            "price_reference": {},
        }
    ]

    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry_data))

    r = PoolRegistry(path=path)
    r.load()
    pool = r.get("0xabc1")

    assert pool.tick_lower == -887272
    assert pool.tick_upper == 887272


def test_registry_validate_catches_inverted_ticks(tmp_path):
    import json
    from registry.registry import PoolRegistry

    registry_data = [
        {
            "pool_address": "0xabc2",
            "pair_name": "A-B",
            "token0": {"symbol": "A", "address": "0xaaa", "decimals": 18},
            "token1": {"symbol": "B", "address": "0xbbb", "decimals": 18},
            "fee_tier": 500,
            "tick_lower": 1000,
            "tick_upper": -1000,
            "price_reference": {},
        }
    ]

    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry_data))

    r = PoolRegistry(path=path)
    r.load()
    errors = r.validate()

    assert any("tick_lower" in e for e in errors)


def test_real_registry_json_has_tick_fields():
    import json
    from pathlib import Path

    path = Path("registry/registry.json")
    data = json.loads(path.read_text())

    assert isinstance(data, list)
    assert len(data) == 15

    for entry in data:
        pair = entry.get("pair_name", "UNKNOWN")
        assert "tick_lower" in entry, f"{pair}: missing tick_lower"
        assert "tick_upper" in entry, f"{pair}: missing tick_upper"
        assert entry["tick_lower"] < entry["tick_upper"], (
            f"{pair}: tick_lower {entry['tick_lower']} >= tick_upper {entry['tick_upper']}"
        )


# ---------------------------------------------------------------------------
# Sprint 16 — fee_tier validity regression guard
# ---------------------------------------------------------------------------

_VALID_FEE_TIERS = {100, 500, 3000, 10000}

def test_real_registry_json_all_fee_tiers_valid():
    """
    Guard: every pool in the committed registry.json must have a fee_tier
    in the Uniswap V3 valid set {100, 500, 3000, 10000}.
    This test will fail if an invalid basis-point value is re-introduced.
    """
    import json
    from pathlib import Path

    path = Path("registry/registry.json")
    data = json.loads(path.read_text())

    assert isinstance(data, list)
    assert len(data) == 15

    for entry in data:
        pair = entry.get("pair_name", "UNKNOWN")
        fee = entry.get("fee_tier")
        assert fee in _VALID_FEE_TIERS, (
            f"{pair}: fee_tier {fee} not in valid set {_VALID_FEE_TIERS}"
        )
