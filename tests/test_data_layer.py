"""Tests for Sprint 2 — Data Layer."""

import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models import PoolDayData, PoolHistoryPoint, TokenHistoryPoint
from data.fetcher.base import AbstractFetcher, FetchError, RateLimitError
from data.fetcher.router import FetchRouter
from data.loader.pool_loader import load_pool_history, save_pool_history
from data.loader.token_loader import save_token_history, load_token_history


# ============================================================================
# Fixtures
# ============================================================================

def _sample_graph_response(page_size: int = 5) -> list[dict]:
    """Generate a page of mock The Graph poolDayData records."""
    base_date = 1700000000
    return [
        {
            "date": str(base_date + i * 86400),
            "volumeUSD": f"1000.{i}",
            "tvlUSD": f"50000.{i}",
            "token0Price": f"1.0{i}",
            "token1Price": f"2.0{i}",
            "feeGrowthGlobal0X128": str(1000 + i) if i % 2 == 0 else "0",
            "feeGrowthGlobal1X128": str(2000 + i) if i % 3 != 0 else None,
        }
        for i in range(page_size)
    ]


def _make_pool_day_data(date_offset: int = 0) -> PoolDayData:
    base_date = 1700000000
    return PoolDayData(
        pool_address="0xabc".lower(),
        date=base_date + date_offset * 86400,
        price_token1_in_token0=Decimal("2.0"),
        price_token0_in_token1=Decimal("1.0"),
        volume_usd=Decimal("1000.0"),
        tvl_usd=Decimal("50000.0"),
        fee_growth_global_0=1000,
        fee_growth_global_1=None,
        source="the_graph",
    )


# ============================================================================
# TheGraphFetcher tests
# ============================================================================

class TestTheGraphFetcher:
    """Tests for data.fetcher.the_graph.TheGraphFetcher."""

    @pytest.fixture(autouse=True)
    def _fetcher(self):
        from data.fetcher.the_graph import TheGraphFetcher
        self.fetcher = TheGraphFetcher(url="https://api.studio.thegraph.com/query/123", rate_limit_per_min=30)

    def test_the_graph_fetcher_name_is_the_graph(self):
        assert self.fetcher.name == "the_graph"

    def test_the_graph_single_page_returns_pool_day_data(self):
        page = _sample_graph_response(3)

        calls = iter([
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": page}}),
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": []}}),
        ])

        def side_effect(*a, **kw):
            return next(calls)

        with patch("requests.post", side_effect=side_effect):
            results = self.fetcher.fetch_pool_history("0xABC", days=3)

        assert len(results) == 3
        assert all(isinstance(r, PoolDayData) for r in results)
        assert results[0].pool_address == "0xabc"
        assert isinstance(results[0].price_token1_in_token0, Decimal)
        assert isinstance(results[0].volume_usd, Decimal)

    def test_the_graph_paginates_until_empty(self):
        page1 = _sample_graph_response(3)
        page2 = _sample_graph_response(2)

        calls = iter([
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": page1}}),
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": page2}}),
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": []}}),
        ])

        def side_effect(*a, **kw):
            return next(calls)

        with patch("requests.post", side_effect=side_effect):
            results = self.fetcher.fetch_pool_history("0xABC", days=30)

        assert len(results) == 5

    def test_the_graph_raises_rate_limit_on_429(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RateLimitError):
                self.fetcher.fetch_pool_history("0xABC", days=7)

    def test_the_graph_raises_fetch_error_on_500(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(FetchError, match="500"):
                self.fetcher.fetch_pool_history("0xABC", days=7)

    def test_the_graph_fee_growth_null_becomes_none(self):
        page = [
            {
                "date": "1700000000",
                "volumeUSD": "1000.0",
                "tvlUSD": "50000.0",
                "token0Price": "1.0",
                "token1Price": "2.0",
                "feeGrowthGlobal0X128": None,
                "feeGrowthGlobal1X128": "0",
            }
        ]

        calls = iter([
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": page}}),
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": []}}),
        ])

        def side_effect(*a, **kw):
            return next(calls)

        with patch("requests.post", side_effect=side_effect):
            results = self.fetcher.fetch_pool_history("0xABC", days=1)

        assert results[0].fee_growth_global_0 is None
        assert results[0].fee_growth_global_1 is None

    def test_the_graph_is_available_true_when_url_set(self):
        assert self.fetcher.is_available() is True

    def test_the_graph_is_available_false_when_url_empty(self):
        from data.fetcher.the_graph import TheGraphFetcher
        empty_fetcher = TheGraphFetcher(url="")
        assert empty_fetcher.is_available() is False


# ============================================================================
# CoinGeckoFetcher tests
# ============================================================================

class TestCoinGeckoFetcher:
    """Tests for data.fetcher.coingecko.CoinGeckoFetcher."""

    @pytest.fixture(autouse=True)
    def _fetcher(self):
        from data.fetcher.coingecko import CoinGeckoFetcher
        self.fetcher = CoinGeckoFetcher(api_key="test-key", rate_limit_per_min=30)

    def test_coingecko_token_history_constructs_pool_day_data(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "prices": [[1700000000000, 100.0], [1700086400000, 105.0]],
            "total_volumes": [[1700000000000, 5000.0], [1700086400000, 6000.0]],
        }

        with patch("requests.get", return_value=mock_resp):
            results = self.fetcher.fetch_token_history("ethereum", days=7)

        assert len(results) == 2
        assert isinstance(results[0].price_token1_in_token0, Decimal)
        assert results[0].source == "coingecko"

    def test_coingecko_fee_growth_always_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "prices": [[1700000000000, 100.0]],
            "total_volumes": [[1700000000000, 5000.0]],
        }

        with patch("requests.get", return_value=mock_resp):
            results = self.fetcher.fetch_token_history("ethereum", days=1)

        assert results[0].fee_growth_global_0 is None
        assert results[0].fee_growth_global_1 is None

    def test_coingecko_tvl_always_zero(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "prices": [[1700000000000, 100.0]],
            "total_volumes": [[1700000000000, 5000.0]],
        }

        with patch("requests.get", return_value=mock_resp):
            results = self.fetcher.fetch_token_history("ethereum", days=1)

        assert results[0].tvl_usd == Decimal("0")

    def test_coingecko_raises_rate_limit_on_429(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(RateLimitError):
                self.fetcher.fetch_token_history("ethereum", days=7)

    def test_coingecko_fetch_pool_history_returns_pool_day_data(self, tmp_path):
        registry_file = tmp_path / "registry.json"
        with open(registry_file, "w") as f:
            json.dump([{
                "pool_address": "0xpool",
                "token0": {"symbol": "USDC"},
                "token1": {"symbol": "WETH"},
            }], f)

        from data.fetcher.coingecko import CoinGeckoFetcher
        fetcher = CoinGeckoFetcher(
            api_key="test-key",
            rate_limit_per_min=30,
            registry_path=registry_file,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "prices": [[1700000000000, 100.0], [1700086400000, 105.0]],
            "total_volumes": [[1700000000000, 5000.0], [1700086400000, 6000.0]],
        }

        with patch("requests.get", return_value=mock_resp):
            results = fetcher.fetch_pool_history("0xpool", days=7)

        assert len(results) == 2
        assert results[0].pool_address == "0xpool"
        assert results[0].source == "coingecko"
        assert isinstance(results[0].price_token1_in_token0, Decimal)

    def test_coingecko_fetch_pool_history_raises_when_pool_not_in_registry(self, tmp_path):
        registry_file = tmp_path / "registry.json"
        with open(registry_file, "w") as f:
            json.dump([], f)

        from data.fetcher.coingecko import CoinGeckoFetcher
        fetcher = CoinGeckoFetcher(
            api_key="test-key",
            rate_limit_per_min=30,
            registry_path=registry_file,
        )

        with pytest.raises(FetchError, match="not found in registry"):
            fetcher.fetch_pool_history("0xunknown", days=7)

    def test_coingecko_fetch_pool_history_raises_when_no_coin_id_mapping(self, tmp_path):
        registry_file = tmp_path / "registry.json"
        with open(registry_file, "w") as f:
            json.dump([{
                "pool_address": "0xpool",
                "token0": {"symbol": "UNKNOWN"},
                "token1": {"symbol": "ALSO_UNKNOWN"},
            }], f)

        from data.fetcher.coingecko import CoinGeckoFetcher
        fetcher = CoinGeckoFetcher(
            api_key="test-key",
            rate_limit_per_min=30,
            registry_path=registry_file,
        )

        with pytest.raises(FetchError, match="no coin_id mapping"):
            fetcher.fetch_pool_history("0xpool", days=7)

    def test_coingecko_fetch_pool_history_restamps_pool_address(self, tmp_path):
        registry_file = tmp_path / "registry.json"
        with open(registry_file, "w") as f:
            json.dump([{
                "pool_address": "0xpool",
                "token0": {"symbol": "USDC"},
                "token1": {"symbol": "WETH"},
            }], f)

        from data.fetcher.coingecko import CoinGeckoFetcher
        fetcher = CoinGeckoFetcher(
            api_key="test-key",
            rate_limit_per_min=30,
            registry_path=registry_file,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "prices": [[1700000000000, 100.0]],
            "total_volumes": [[1700000000000, 5000.0]],
        }

        with patch("requests.get", return_value=mock_resp):
            results = fetcher.fetch_pool_history("0xpool", days=7)

        assert all(r.pool_address == "0xpool" for r in results)

    def test_coingecko_fetch_pool_history_falls_back_to_token0_when_token1_unmapped(self, tmp_path):
        registry_file = tmp_path / "registry.json"
        with open(registry_file, "w") as f:
            json.dump([{
                "pool_address": "0xpool",
                "token0": {"symbol": "WETH"},
                "token1": {"symbol": "UNMAPPED"},
            }], f)

        from data.fetcher.coingecko import CoinGeckoFetcher
        fetcher = CoinGeckoFetcher(
            api_key="test-key",
            rate_limit_per_min=30,
            registry_path=registry_file,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "prices": [[1700000000000, 100.0]],
            "total_volumes": [[1700000000000, 5000.0]],
        }

        with patch("requests.get", return_value=mock_resp):
            results = fetcher.fetch_pool_history("0xpool", days=7)

        assert len(results) == 1

    def test_the_graph_sends_auth_header_when_api_key_set(self):
        from data.fetcher.the_graph import TheGraphFetcher
        fetcher = TheGraphFetcher(url="https://example.com/graphql", api_key="mykey")

        page = _sample_graph_response(1)
        calls = iter([
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": page}}),
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": []}}),
        ])

        def side_effect(*a, **kw):
            return next(calls)

        with patch("requests.post", side_effect=side_effect) as mock_post:
            fetcher.fetch_pool_history("0xABC", days=7)

        headers = mock_post.call_args.kwargs.get("headers", {})
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer mykey"

    def test_the_graph_no_auth_header_when_api_key_empty(self):
        from data.fetcher.the_graph import TheGraphFetcher
        fetcher = TheGraphFetcher(url="https://example.com/graphql", api_key="")

        page = _sample_graph_response(1)
        calls = iter([
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": page}}),
            MagicMock(status_code=200, json=lambda: {"data": {"poolDayDatas": []}}),
        ])

        def side_effect(*a, **kw):
            return next(calls)

        with patch("requests.post", side_effect=side_effect) as mock_post:
            fetcher.fetch_pool_history("0xABC", days=7)

        headers = mock_post.call_args.kwargs.get("headers", {})
        assert "Authorization" not in headers

    def test_the_graph_raises_fetch_error_on_401(self):
        from data.fetcher.the_graph import TheGraphFetcher
        fetcher = TheGraphFetcher(url="https://example.com/graphql", api_key="bad")

        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(FetchError, match="401"):
                fetcher.fetch_pool_history("0xABC", days=7)


# ============================================================================
# DeFiLlamaFetcher tests
# ============================================================================

class TestDeFiLlamaFetcher:
    """Tests for data.fetcher.defillama.DeFiLlamaFetcher."""

    @pytest.fixture(autouse=True)
    def _fetcher(self):
        from data.fetcher.defillama import DeFiLlamaFetcher
        self.fetcher = DeFiLlamaFetcher(protocol_slug="aerodrome-finance", rate_limit_per_min=100)

    def test_defillama_tvl_parsed_correctly(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tvl": [
                {"date": 1700000000, "totalLiquidityUSD": 50000.0},
                {"date": 1700086400, "totalLiquidityUSD": 55000.0},
            ]
        }

        with patch("requests.get", return_value=mock_resp):
            results = self.fetcher.fetch_pool_history("0xabc", days=7)

        assert len(results) == 2
        assert results[0].tvl_usd == Decimal("50000.0")
        assert results[1].tvl_usd == Decimal("55000.0")

    def test_defillama_price_fields_are_zero(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tvl": [{"date": 1700000000, "totalLiquidityUSD": 50000.0}]
        }

        with patch("requests.get", return_value=mock_resp):
            results = self.fetcher.fetch_pool_history("0xabc", days=7)

        assert results[0].price_token1_in_token0 == Decimal("0")
        assert results[0].price_token0_in_token1 == Decimal("0")

    def test_defillama_fee_growth_always_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tvl": [{"date": 1700000000, "totalLiquidityUSD": 50000.0}]
        }

        with patch("requests.get", return_value=mock_resp):
            results = self.fetcher.fetch_pool_history("0xabc", days=7)

        assert results[0].fee_growth_global_0 is None
        assert results[0].fee_growth_global_1 is None

    def test_defillama_raises_rate_limit_on_429(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(RateLimitError):
                self.fetcher.fetch_pool_history("0xabc", days=7)


# ============================================================================
# FetchRouter tests
# ============================================================================

class TestFetchRouter:
    """Tests for data.fetcher.router.FetchRouter."""

    def _make_mock_fetcher(
        self,
        name: str = "mock",
        return_value: list[PoolDayData] | None = None,
        raise_exc: Exception | None = None,
        available: bool = True,
    ) -> MagicMock:
        """Create a mock fetcher with configurable behavior."""
        m = MagicMock(spec=AbstractFetcher)
        m.name = name
        m.is_available.return_value = available
        if raise_exc:
            m.fetch_pool_history.side_effect = raise_exc
        elif return_value is not None:
            m.fetch_pool_history.return_value = return_value
        else:
            m.fetch_pool_history.return_value = []
        return m

    def test_router_returns_first_source_result(self):
        rec = _make_pool_day_data()
        f1 = self._make_mock_fetcher(return_value=[rec])
        f2 = self._make_mock_fetcher(return_value=[rec])

        router = FetchRouter(fetchers=[f1, f2])
        result = router.fetch("0xabc", days=7)

        assert len(result) == 1
        f1.fetch_pool_history.assert_called_once()
        f2.fetch_pool_history.assert_not_called()

    def test_router_falls_back_on_rate_limit_error(self):
        rec = _make_pool_day_data()
        f1 = self._make_mock_fetcher(raise_exc=RateLimitError(), available=True)
        f2 = self._make_mock_fetcher(return_value=[rec])

        router = FetchRouter(fetchers=[f1, f2])
        result = router.fetch("0xabc", days=7)

        assert len(result) == 1
        f2.fetch_pool_history.assert_called_once()

    def test_router_raises_on_fetch_error_no_fallback(self):
        f1 = self._make_mock_fetcher(raise_exc=FetchError("hard fail"))
        f2 = self._make_mock_fetcher(return_value=[_make_pool_day_data()])

        router = FetchRouter(fetchers=[f1, f2])
        with pytest.raises(FetchError, match="hard fail"):
            router.fetch("0xabc", days=7)

        f2.fetch_pool_history.assert_not_called()

    def test_router_skips_unavailable_fetcher(self):
        rec = _make_pool_day_data()
        f1 = self._make_mock_fetcher(available=False)
        f2 = self._make_mock_fetcher(return_value=[rec])

        router = FetchRouter(fetchers=[f1, f2])
        result = router.fetch("0xabc", days=7)

        assert len(result) == 1
        f1.fetch_pool_history.assert_not_called()

    def test_router_raises_when_all_exhausted(self):
        f1 = self._make_mock_fetcher(raise_exc=RateLimitError())
        f2 = self._make_mock_fetcher(return_value=[])

        router = FetchRouter(fetchers=[f1, f2])
        with pytest.raises(FetchError, match="All sources exhausted"):
            router.fetch("0xabc", days=7)

    def test_router_falls_back_on_empty_result(self):
        rec = _make_pool_day_data()
        f1 = self._make_mock_fetcher(return_value=[])
        f2 = self._make_mock_fetcher(return_value=[rec])

        router = FetchRouter(fetchers=[f1, f2])
        result = router.fetch("0xabc", days=7)

        assert len(result) == 1


# ============================================================================
# PoolLoader tests
# ============================================================================

class TestPoolLoader:

    def _write_json(self, path: Path, data: dict) -> None:
        with open(path, "w") as f:
            json.dump(data, f)

    def test_load_pool_history_v1_camel_case_columns(self, tmp_path):
        file = tmp_path / "pool.json"
        self._write_json(file, {
            "pool_address": "0xABC",
            "days": [
                {
                    "date": 1700000000,
                    "volumeUSD": "1000.0",
                    "tvlUSD": "50000.0",
                    "token0Price": "1.0",
                    "token1Price": "2.0",
                    "feeGrowthGlobal0X128": "1000",
                    "feeGrowthGlobal1X128": None,
                }
            ],
        })

        results = load_pool_history(file)
        assert len(results) == 1
        assert results[0].volume_usd == Decimal("1000.0")
        assert results[0].tvl_usd == Decimal("50000.0")
        assert results[0].fee_growth_global_0 == 1000
        assert results[0].fee_growth_global_1 is None

    def test_load_pool_history_v2_snake_case_columns(self, tmp_path):
        file = tmp_path / "pool.json"
        self._write_json(file, {
            "pool_address": "0xABC",
            "days": [
                {
                    "date": 1700000000,
                    "volume_usd": "2000.0",
                    "tvl_usd": "60000.0",
                    "token0_price": "1.5",
                    "token1_price": "3.0",
                    "fee_growth_global_0": "2000",
                    "fee_growth_global_1": "3000",
                }
            ],
        })

        results = load_pool_history(file)
        assert len(results) == 1
        assert results[0].volume_usd == Decimal("2000.0")
        assert results[0].fee_growth_global_0 == 2000
        assert results[0].fee_growth_global_1 == 3000

    def test_load_pool_history_fee_growth_null_becomes_none(self, tmp_path):
        file = tmp_path / "pool.json"
        self._write_json(file, {
            "pool_address": "0xABC",
            "days": [
                {
                    "date": 1700000000,
                    "volumeUSD": "1000.0",
                    "tvlUSD": "50000.0",
                    "token0Price": "1.0",
                    "token1Price": "2.0",
                    "feeGrowthGlobal0X128": None,
                    "feeGrowthGlobal1X128": "0",
                }
            ],
        })

        results = load_pool_history(file)
        assert results[0].fee_growth_global_0 is None
        assert results[0].fee_growth_global_1 is None

    def test_load_pool_history_skips_zero_volume_and_tvl_rows(self, tmp_path):
        file = tmp_path / "pool.json"
        self._write_json(file, {
            "pool_address": "0xABC",
            "days": [
                {
                    "date": 1700000000,
                    "volumeUSD": "0",
                    "tvlUSD": "0",
                    "token0Price": "1.0",
                    "token1Price": "2.0",
                },
                {
                    "date": 1700086400,
                    "volumeUSD": "500.0",
                    "tvlUSD": "50000.0",
                    "token0Price": "1.0",
                    "token1Price": "2.0",
                },
            ],
        })

        results = load_pool_history(file)
        assert len(results) == 1
        assert results[0].date == 1700086400

    def test_load_pool_history_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_pool_history(Path("/nonexistent/pool.json"))

    def test_load_pool_history_raises_value_error_on_bad_json(self, tmp_path):
        file = tmp_path / "pool.json"
        with open(file, "w") as f:
            f.write("{not valid json}")

        with pytest.raises(ValueError, match="Malformed JSON"):
            load_pool_history(file)

    def test_save_and_reload_roundtrip(self, tmp_path):
        file = tmp_path / "pool.json"
        records = [
            PoolDayData(
                pool_address="0xabc",
                date=1700000000,
                price_token1_in_token0=Decimal("2.0"),
                price_token0_in_token1=Decimal("1.0"),
                volume_usd=Decimal("1000.0"),
                tvl_usd=Decimal("50000.0"),
                fee_growth_global_0=1000,
                fee_growth_global_1=None,
                source="the_graph",
            ),
        ]

        save_pool_history("0xabc", "USDC-ETH", records, file)
        loaded = load_pool_history(file)

        assert len(loaded) == 1
        assert loaded[0].volume_usd == Decimal("1000.0")
        assert loaded[0].fee_growth_global_0 == 1000
        assert loaded[0].fee_growth_global_1 is None

    def test_load_pool_history_sorts_ascending_by_date(self, tmp_path):
        file = tmp_path / "pool.json"
        self._write_json(file, {
            "pool_address": "0xABC",
            "days": [
                {
                    "date": 1700086400,
                    "volumeUSD": "2000.0",
                    "tvlUSD": "55000.0",
                    "token0Price": "1.1",
                    "token1Price": "2.1",
                },
                {
                    "date": 1700000000,
                    "volumeUSD": "1000.0",
                    "tvlUSD": "50000.0",
                    "token0Price": "1.0",
                    "token1Price": "2.0",
                },
            ],
        })

        results = load_pool_history(file)
        assert len(results) == 2
        assert results[0].date < results[1].date


# ============================================================================
# GeckoTerminalFetcher hourly tests (Sprint 9)
# ============================================================================

class TestGeckoTerminalHourly:
    """Tests that GeckoTerminalFetcher preserves hourly timestamps."""

    @pytest.fixture(autouse=True)
    def _fetcher(self):
        from data.fetcher.gecko_terminal import GeckoTerminalFetcher
        self.fetcher = GeckoTerminalFetcher(
            network="base",
            timeframe="hour",
            rate_limit_per_min=25,
        )

    def test_preserves_hourly_timestamps_no_daily_collapse(self):
        """Multi-day mocked candles return > 24 records with distinct timestamps."""
        # Simulate 3 days of hourly data = 72 unique timestamps
        candles = []
        base_ts = 1700000000
        for i in range(72):
            candles.append({
                "timestamp": base_ts + i * 3600,
                "close": f"2000.{i:04d}",
                "volume": f"1000.{i:04d}",
            })

        detail_mock = MagicMock()
        detail_mock.status_code = 200
        detail_mock.json.return_value = {
            "data": {
                "pair": {"id": "0xabc"},
                "pool": {"totalValueLockedUSD": "50000.0"},
            }
        }

        history_mock = MagicMock()
        history_mock.status_code = 200
        history_mock.json.return_value = {
            "data": {"pair": {"candleChartOverTime": candles}}
        }

        calls = iter([detail_mock, history_mock])
        def side_effect(*a, **kw):
            return next(calls)

        with patch("requests.get", side_effect=side_effect):
            results = self.fetcher.fetch_pool_history("0xabc", days=3)

        assert len(results) == 72
        # Verify timestamps are hourly (not daily-bucketed)
        assert all(hasattr(r, "timestamp") for r in results)
        unique_ts = set(r.timestamp for r in results)
        assert len(unique_ts) == 72

    def test_dedup_by_exact_timestamp(self):
        """Duplicate timestamps are deduplicated, keeping last."""
        candles = [
            {"timestamp": 1700000000, "close": "2000.0", "volume": "1000.0"},
            {"timestamp": 1700003600, "close": "2050.0", "volume": "1100.0"},
            {"timestamp": 1700003600, "close": "2060.0", "volume": "1200.0"},  # dup
        ]

        detail_mock = MagicMock()
        detail_mock.status_code = 200
        detail_mock.json.return_value = {
            "data": {"pair": {"id": "0xabc"}, "pool": {"totalValueLockedUSD": "50000.0"}}
        }

        history_mock = MagicMock()
        history_mock.status_code = 200
        history_mock.json.return_value = {
            "data": {"pair": {"candleChartOverTime": candles}}
        }

        calls = iter([detail_mock, history_mock])
        def side_effect(*a, **kw):
            return next(calls)

        with patch("requests.get", side_effect=side_effect):
            results = self.fetcher.fetch_pool_history("0xabc", days=1)

        assert len(results) == 2
        # Second record should have the deduped value (last wins)
        assert results[1].price_token1_in_token0 == Decimal("2060.0")


# ============================================================================
# PoolLoader hourly persistence tests (Sprint 9)
# ============================================================================

class TestPoolLoaderHourly:
    """Tests that pool_loader correctly handles PoolHistoryPoint records."""

    def test_save_pool_history_hourly_includes_timestamp(self, tmp_path):
        file = tmp_path / "pool.json"
        records = [
            PoolHistoryPoint(
                pool_address="0xabc",
                timestamp=1700000000,
                price_token1_in_token0=Decimal("2.0"),
                price_token0_in_token1=Decimal("0.5"),
                volume_usd=Decimal("1000.0"),
                tvl_usd=Decimal("50000.0"),
                fee_growth_global_0=None,
                fee_growth_global_1=None,
                source="gecko_terminal",
            ),
            PoolHistoryPoint(
                pool_address="0xabc",
                timestamp=1700003600,
                price_token1_in_token0=Decimal("2.1"),
                price_token0_in_token1=Decimal("0.476"),
                volume_usd=Decimal("1100.0"),
                tvl_usd=Decimal("51000.0"),
                fee_growth_global_0=None,
                fee_growth_global_1=None,
                source="gecko_terminal",
            ),
        ]

        save_pool_history("0xabc", "USDC-ETH", records, file)

        import json as _json
        with open(file) as f:
            data = _json.load(f)

        days = data["days"]
        assert len(days) == 2
        # Hourly records have timestamp, not date
        assert "timestamp" in days[0]
        assert days[0]["timestamp"] == 1700000000
        assert "date" not in days[0]

    def test_save_pool_history_daily_still_has_date(self, tmp_path):
        file = tmp_path / "pool.json"
        records = [
            PoolDayData(
                pool_address="0xabc",
                date=1700000000,
                price_token1_in_token0=Decimal("2.0"),
                price_token0_in_token1=Decimal("0.5"),
                volume_usd=Decimal("1000.0"),
                tvl_usd=Decimal("50000.0"),
                fee_growth_global_0=1000,
                fee_growth_global_1=None,
                source="the_graph",
            ),
        ]

        save_pool_history("0xabc", "USDC-ETH", records, file)

        import json as _json
        with open(file) as f:
            data = _json.load(f)

        assert "date" in data["days"][0]
        assert "timestamp" not in data["days"][0]


# ============================================================================
# TokenLoader tests (Sprint 9)
# ============================================================================

class TestTokenLoader:
    """Tests for data.loader.token_loader."""

    def test_save_and_load_token_history_roundtrip(self, tmp_path):
        file = tmp_path / "WETH.json"
        records = [
            TokenHistoryPoint(
                token_address="0xeth",
                symbol="WETH",
                timestamp=1700000000,
                price_usd=Decimal("2000.50"),
                volume_usd=Decimal("50000000.0"),
                market_cap_usd=Decimal("240000000000.0"),
                source="coingecko",
            ),
            TokenHistoryPoint(
                token_address="0xeth",
                symbol="WETH",
                timestamp=1700003600,
                price_usd=Decimal("2050.75"),
                volume_usd=Decimal("55000000.0"),
                market_cap_usd=None,
                source="coingecko",
            ),
        ]

        save_token_history("0xeth", "WETH", records, file)
        loaded = load_token_history(file)

        assert len(loaded) == 2
        assert loaded[0].price_usd == Decimal("2000.50")
        assert loaded[0].market_cap_usd == Decimal("240000000000.0")
        assert loaded[1].market_cap_usd is None
        assert loaded[1].timestamp == 1700003600

    def test_save_token_history_creates_parent_dir(self, tmp_path):
        file = tmp_path / "nested" / "dir" / "TOKEN.json"
        records = [
            TokenHistoryPoint(
                token_address="0xtok",
                symbol="TOKEN",
                timestamp=1700000000,
                price_usd=Decimal("1.0"),
                volume_usd=Decimal("100.0"),
                market_cap_usd=None,
                source="coingecko",
            ),
        ]

        result = save_token_history("0xtok", "TOKEN", records, file)
        assert result == file
        assert file.exists()


# ============================================================================
# TokenPriceFetcher tests (Sprint 9)
# ============================================================================

class TestTokenPriceFetcher:
    """Tests for data.fetcher.token_prices.TokenPriceFetcher."""

    @pytest.fixture(autouse=True)
    def _fetcher(self, tmp_path):
        from data.fetcher.token_prices import TokenPriceFetcher
        registry_file = tmp_path / "registry.json"
        with open(registry_file, "w") as f:
            json.dump([], f)
        self.fetcher = TokenPriceFetcher(
            api_key="test-key",
            rate_limit_per_min=30,
            registry_path=registry_file,
        )

    def test_normalizes_prices_volumes_market_caps(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "prices": [
                [1700000000000, 2000.5],
                [1700086400000, 2100.75],
            ],
            "total_volumes": [
                [1700000000000, 50000000.0],
                [1700086400000, 55000000.0],
            ],
            "market_caps": [
                [1700000000000, 240000000000.0],
                [1700086400000, 252000000000.0],
            ],
        }

        with patch("requests.get", return_value=mock_resp):
            results = self.fetcher.fetch_token_history(
                token_symbol="WETH",
                token_address="0xeth",
                days=7,
            )

        assert len(results) == 2
        assert all(isinstance(r, TokenHistoryPoint) for r in results)
        assert results[0].price_usd == Decimal("2000.5")
        assert results[0].volume_usd == Decimal("50000000.0")
        assert results[0].market_cap_usd == Decimal("240000000000.0")
        assert results[0].source == "coingecko"

    def test_timestamps_bucketed_to_hour(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Timestamp not aligned to hour boundary
        mock_resp.json.return_value = {
            "prices": [[1700000100000, 2000.0]],
            "total_volumes": [[1700000100000, 50000.0]],
        }

        with patch("requests.get", return_value=mock_resp):
            results = self.fetcher.fetch_token_history(
                token_symbol="WETH",
                token_address="0xeth",
                days=7,
            )

        # 1700000100000 ms -> bucketed to hour: (1700000100 // 3600) * 3600 = 1700000100 - 100
        assert results[0].timestamp == (1700000100 // 3600) * 3600

    def test_raises_rate_limit_on_429(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(RateLimitError):
                self.fetcher.fetch_token_history(
                    token_symbol="WETH",
                    token_address="0xeth",
                    days=7,
                )

    def test_raises_fetch_error_on_500(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(FetchError):
                self.fetcher.fetch_token_history(
                    token_symbol="WETH",
                    token_address="0xeth",
                    days=7,
                )

    def test_is_available_checks_ping(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("requests.get", return_value=mock_resp):
            assert self.fetcher.is_available() is True
