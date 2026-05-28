import pytest
import respx
import httpx
from urllib.parse import parse_qs, urlparse
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from server import _do_instant_query, _do_range_query

FAKE = "http://fake-prometheus:9090"

INSTANT_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [{"metric": {"instance": "host1"}, "value": [1234567890, "95.5"]}],
    },
}

RANGE_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "matrix",
        "result": [{"metric": {}, "values": [[1234567890, "90"], [1234567950, "92"]]}],
    },
}


@pytest.mark.asyncio
@respx.mock
async def test_instant_query_calls_query_endpoint():
    route = respx.get(f"{FAKE}/api/v1/query").mock(
        return_value=httpx.Response(200, json=INSTANT_RESPONSE)
    )
    result = await _do_instant_query(
        expr="100*(1-avg by(instance)(irate(node_cpu_seconds_total{mode='idle'}[5m])))",
        prometheus_url=FAKE,
    )
    assert route.called
    assert result["status"] == "success"
    assert result["result"][0]["value"][1] == "95.5"


@pytest.mark.asyncio
@respx.mock
async def test_instant_query_passes_time_param():
    route = respx.get(f"{FAKE}/api/v1/query").mock(
        return_value=httpx.Response(200, json=INSTANT_RESPONSE)
    )
    await _do_instant_query(expr="up", time="1698400000", prometheus_url=FAKE)
    params = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    assert params["time"][0] == "1698400000"


@pytest.mark.asyncio
@respx.mock
async def test_range_query_converts_iso_timestamp():
    route = respx.get(f"{FAKE}/api/v1/query_range").mock(
        return_value=httpx.Response(200, json=RANGE_RESPONSE)
    )
    result = await _do_range_query(
        expr="up",
        start="2023-10-27T10:00:00Z",
        duration_minutes=30,
        prometheus_url=FAKE,
    )
    assert route.called
    assert result["status"] == "success"
    params = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    assert "start" in params
    assert "end" in params
    assert float(params["end"][0]) > float(params["start"][0])


@pytest.mark.asyncio
@respx.mock
async def test_range_query_end_is_start_plus_duration():
    route = respx.get(f"{FAKE}/api/v1/query_range").mock(
        return_value=httpx.Response(200, json=RANGE_RESPONSE)
    )
    await _do_range_query(
        expr="up",
        start="2023-10-27T10:00:00Z",
        duration_minutes=15,
        prometheus_url=FAKE,
    )
    params = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    start_ts = float(params["start"][0])
    end_ts = float(params["end"][0])
    assert abs((end_ts - start_ts) - 15 * 60) < 1


@pytest.mark.asyncio
@respx.mock
async def test_range_query_explicit_end_overrides_duration():
    route = respx.get(f"{FAKE}/api/v1/query_range").mock(
        return_value=httpx.Response(200, json=RANGE_RESPONSE)
    )
    await _do_range_query(
        expr="up",
        start="2023-10-27T10:00:00Z",
        end="2023-10-27T10:05:00Z",
        duration_minutes=30,
        prometheus_url=FAKE,
    )
    params = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    start_ts = float(params["start"][0])
    end_ts = float(params["end"][0])
    assert abs((end_ts - start_ts) - 5 * 60) < 1


@pytest.mark.asyncio
@respx.mock
async def test_instant_query_raises_on_prometheus_error():
    respx.get(f"{FAKE}/api/v1/query").mock(
        return_value=httpx.Response(200, json={
            "status": "error",
            "errorType": "bad_data",
            "error": "parse error: unexpected end of input",
        })
    )
    with pytest.raises(RuntimeError, match="Prometheus error"):
        await _do_instant_query(expr="invalid{{", prometheus_url=FAKE)


@pytest.mark.asyncio
@respx.mock
async def test_range_query_raises_on_prometheus_error():
    respx.get(f"{FAKE}/api/v1/query_range").mock(
        return_value=httpx.Response(200, json={
            "status": "error",
            "errorType": "bad_data",
            "error": "parse error: unexpected end of input",
        })
    )
    with pytest.raises(RuntimeError, match="Prometheus error"):
        await _do_range_query(expr="invalid{{", start="2023-10-27T10:00:00Z", prometheus_url=FAKE)
