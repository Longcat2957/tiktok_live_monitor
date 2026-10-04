import json
import sys

import pytest

from profile_pipeline import main, run_profile


async def test_profile_counts_and_preserves_order() -> None:
    result = await run_profile(events=20, rate=200, clients=2, source_capacity=20)

    assert result["source_drops"] == result["slow_disconnects"] == 0
    assert result["source_queue_peak"] <= 20
    assert result["peer_queue_peak"] <= 100
    assert result["drain_timed_out"] is False
    for client in result["clients"]:
        assert (client["received"], client["first_sequence"], client["last_sequence"]) == (
            20,
            0,
            19,
        )
        assert client["in_order"] is True
        assert client["connected_at_end"] is True
        assert client["serialized_chars"] > 0
    assert result["latency_ms"]["p50"] <= result["latency_ms"]["p95"]
    assert result["latency_ms"]["p95"] <= result["latency_ms"]["p99"]


async def test_slow_client_does_not_block_fast_client() -> None:
    result = await run_profile(events=30, rate=200, clients=2, peer_capacity=4, slow_client_ms=100)

    assert result["source_drops"] == 0
    assert result["slow_disconnects"] == 1
    fast, slow = result["clients"]
    assert (fast["received"], fast["last_sequence"], fast["in_order"]) == (30, 29, True)
    assert fast["connected_at_end"] is True
    assert slow["received"] < 30
    assert slow["connected_at_end"] is False


def test_cli_reports_cpu_and_heap_profile(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["profile_pipeline.py", "--events", "2", "--profile"])
    main()
    result = json.loads(capsys.readouterr().out)

    assert result["events"] == 2
    assert result["profile"]["python_heap_peak_bytes"] > 0
    assert result["profile"]["cpu_top"]


@pytest.mark.parametrize("option,value", [("--events", "100001"), ("--clients", "17")])
def test_cli_rejects_oversized_measurement(monkeypatch, option, value) -> None:
    monkeypatch.setattr(sys, "argv", ["profile_pipeline.py", option, value])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
