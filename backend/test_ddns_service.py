from unittest.mock import MagicMock, patch


def test_get_public_ip_parses_trace_response() -> None:
    from ddns_service import get_public_ip

    fake_resp = MagicMock()
    fake_resp.read.return_value = b"fl=1\nip=203.0.113.5\nts=123\n"
    fake_resp.__enter__.return_value = fake_resp
    with patch("ddns_service.urllib.request.urlopen", return_value=fake_resp):
        assert get_public_ip() == "203.0.113.5"


def test_get_public_ip_returns_none_on_failure() -> None:
    from ddns_service import get_public_ip

    with patch("ddns_service.urllib.request.urlopen", side_effect=OSError("boom")):
        assert get_public_ip() is None


def test_get_public_ip_returns_none_for_ipv6_address() -> None:
    from ddns_service import get_public_ip

    fake_resp = MagicMock()
    fake_resp.read.return_value = b"fl=1\nip=2001:db8::1\nts=123\n"
    fake_resp.__enter__.return_value = fake_resp
    with patch("ddns_service.urllib.request.urlopen", return_value=fake_resp):
        assert get_public_ip() is None


def test_find_zone_id_picks_longest_matching_suffix() -> None:
    from ddns_service import find_zone_id

    zones_response = {
        "result": [
            {"id": "z-outer", "name": "example.com"},
            {"id": "z-inner", "name": "sub.example.com"},
        ]
    }
    with patch("ddns_service._cf_request", return_value=zones_response):
        assert find_zone_id("tok", "app.sub.example.com") == "z-inner"


def test_find_zone_id_returns_none_when_no_zone_matches() -> None:
    from ddns_service import find_zone_id

    with patch("ddns_service._cf_request", return_value={"result": [{"id": "z1", "name": "other.com"}]}):
        assert find_zone_id("tok", "app.example.com") is None


def test_update_record_patches_only_content_field() -> None:
    from ddns_service import update_record

    with patch("ddns_service._cf_request") as cf_request:
        update_record("tok", "zone1", "rec1", "9.9.9.9")
        cf_request.assert_called_once_with(
            "tok", "/zones/zone1/dns_records/rec1", method="PATCH", body={"content": "9.9.9.9"}
        )


def test_cf_request_raises_when_success_false() -> None:
    from ddns_service import _cf_request

    mock_resp = MagicMock()
    with patch("ddns_service.urllib.request.urlopen") as mock_urlopen, \
         patch("ddns_service.json.load", return_value={"success": False, "errors": ["API error"]}):
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        try:
            _cf_request("tok", "/zones")
            assert False, "Expected RuntimeError"
        except RuntimeError as e:
            assert "API error" in str(e)


def test_sync_skips_update_when_ip_unchanged() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="1.2.3.4"), \
         patch("ddns_service.find_zone_id", return_value="zone1"), \
         patch("ddns_service.find_record", return_value={"id": "rec1", "content": "1.2.3.4"}), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["app.example.com"])
        update_record.assert_not_called()
        assert results == [
            {"domain": "app.example.com", "status": "unchanged", "old_ip": "1.2.3.4", "new_ip": "1.2.3.4", "detail": None}
        ]


def test_sync_updates_record_when_ip_changed() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", return_value="zone1"), \
         patch("ddns_service.find_record", return_value={"id": "rec1", "content": "1.2.3.4"}), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["app.example.com"])
        update_record.assert_called_once_with("tok", "zone1", "rec1", "5.6.7.8")
        assert results == [
            {"domain": "app.example.com", "status": "updated", "old_ip": "1.2.3.4", "new_ip": "5.6.7.8", "detail": None}
        ]


def test_sync_errors_when_public_ip_unavailable() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value=None):
        results = svc.sync("tok", ["app.example.com"])
        assert results[0]["status"] == "error"
        assert results[0]["detail"] == "could not determine public IP"


def test_sync_errors_when_zone_not_found() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", return_value=None):
        results = svc.sync("tok", ["app.example.com"])
        assert results[0]["status"] == "error"
        assert "zone" in results[0]["detail"]


def test_sync_errors_when_record_not_found_and_does_not_create() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", return_value="zone1"), \
         patch("ddns_service.find_record", return_value=None), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["app.example.com"])
        update_record.assert_not_called()
        assert results[0]["status"] == "error"
        assert "record" in results[0]["detail"].lower()


def test_find_record_raises_when_multiple_a_records_found() -> None:
    from ddns_service import find_record

    records_response = {"result": [{"id": "rec1", "content": "1.1.1.1"}, {"id": "rec2", "content": "2.2.2.2"}]}
    with patch("ddns_service._cf_request", return_value=records_response):
        try:
            find_record("tok", "zone1", "app.example.com")
            assert False, "Expected RuntimeError"
        except RuntimeError as e:
            assert "multiple A records" in str(e)


def test_sync_errors_when_multiple_a_records_found() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", return_value="zone1"), \
         patch("ddns_service.find_record", side_effect=RuntimeError("multiple A records found for app.example.com, refusing to guess which to update")), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["app.example.com"])
        update_record.assert_not_called()
        assert results[0]["status"] == "error"
        assert "multiple A records" in results[0]["detail"]


def test_sync_continues_past_one_domains_error() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", side_effect=[None, "zone1"]), \
         patch("ddns_service.find_record", return_value={"id": "rec1", "content": "1.1.1.1"}), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["bad.example.com", "good.example.com"])
        assert results[0]["status"] == "error"
        assert results[1]["status"] == "updated"
        update_record.assert_called_once_with("tok", "zone1", "rec1", "5.6.7.8")


if __name__ == "__main__":
    test_get_public_ip_parses_trace_response()
    test_get_public_ip_returns_none_on_failure()
    test_get_public_ip_returns_none_for_ipv6_address()
    test_find_zone_id_picks_longest_matching_suffix()
    test_find_zone_id_returns_none_when_no_zone_matches()
    test_update_record_patches_only_content_field()
    test_cf_request_raises_when_success_false()
    test_sync_skips_update_when_ip_unchanged()
    test_sync_updates_record_when_ip_changed()
    test_sync_errors_when_public_ip_unavailable()
    test_sync_errors_when_zone_not_found()
    test_sync_errors_when_record_not_found_and_does_not_create()
    test_find_record_raises_when_multiple_a_records_found()
    test_sync_errors_when_multiple_a_records_found()
    test_sync_continues_past_one_domains_error()
    print("ok")
