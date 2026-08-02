import time
from unittest.mock import patch

from icon_service import IconService, _normalize

FAKE_CATALOG = {
    "plex": {"aliases": ["plex-media-server"]},
    "nginx-proxy-manager": {"aliases": ["npm"]},
}


def _service_with_fake_catalog() -> IconService:
    svc = IconService()
    with patch("icon_service.urllib.request.urlopen"), patch("icon_service.json.load", return_value=FAKE_CATALOG):
        svc._fetch()
    return svc


def test_normalize_lowercases_and_collapses_separators() -> None:
    assert _normalize("Plex Media Server") == "plex-media-server"
    assert _normalize("linuxserver/plex") == "linuxserver-plex"


def test_guess_matches_exact_slug() -> None:
    svc = _service_with_fake_catalog()
    assert svc.guess(["plex"]) == "plex"


def test_guess_matches_exact_alias() -> None:
    svc = _service_with_fake_catalog()
    assert svc.guess(["npm"]) == "nginx-proxy-manager"


def test_guess_falls_back_to_fuzzy_within_cutoff() -> None:
    svc = _service_with_fake_catalog()
    assert svc.guess(["plexx"]) == "plex"


def test_guess_returns_none_below_fuzzy_cutoff() -> None:
    svc = _service_with_fake_catalog()
    assert svc.guess(["zzzzznotarealservice"]) is None


def test_guess_skips_candidates_shorter_than_three_chars() -> None:
    svc = _service_with_fake_catalog()
    assert svc.guess(["db"]) is None


def test_guess_prefers_first_candidate_with_an_exact_hit_over_fuzzy_matches_on_earlier_ones() -> None:
    svc = _service_with_fake_catalog()
    # "plexy" only fuzzy-matches "plex"; "npm" is an exact hit further down the list -
    # exact beats fuzzy regardless of candidate order.
    assert svc.guess(["plexy", "npm"]) == "nginx-proxy-manager"


def test_guess_returns_none_when_catalog_fetch_fails() -> None:
    svc = IconService()
    with patch("icon_service.urllib.request.urlopen", side_effect=OSError("no network")):
        assert svc.guess(["plex"]) is None


def test_guess_does_not_block_on_a_slow_fetch() -> None:
    # guess() must return immediately and let the fetch happen on a
    # background thread - a caller (in particular stack_service.scan(),
    # which runs synchronously during app startup) must never stall on
    # network I/O here.
    svc = IconService()
    with patch("icon_service.urllib.request.urlopen", side_effect=lambda *a, **k: time.sleep(0.3)):
        start = time.monotonic()
        assert svc.guess(["plex"]) is None
        assert time.monotonic() - start < 0.1


def test_failed_fetch_does_not_permanently_poison_the_catalog() -> None:
    # A failed fetch clears the in-progress flag (rather than caching an
    # empty catalog forever), so the next guess() call can retry.
    svc = IconService()
    with patch("icon_service.urllib.request.urlopen", side_effect=OSError("no network")):
        svc._fetch()
    assert svc._catalog is None
    assert svc._fetch_in_progress is False
    with patch("icon_service.urllib.request.urlopen"), patch("icon_service.json.load", return_value=FAKE_CATALOG):
        svc._fetch()
    assert svc.guess(["plex"]) == "plex"


if __name__ == "__main__":
    test_normalize_lowercases_and_collapses_separators()
    test_guess_matches_exact_slug()
    test_guess_matches_exact_alias()
    test_guess_falls_back_to_fuzzy_within_cutoff()
    test_guess_returns_none_below_fuzzy_cutoff()
    test_guess_skips_candidates_shorter_than_three_chars()
    test_guess_prefers_first_candidate_with_an_exact_hit_over_fuzzy_matches_on_earlier_ones()
    test_guess_returns_none_when_catalog_fetch_fails()
    test_guess_does_not_block_on_a_slow_fetch()
    test_failed_fetch_does_not_permanently_poison_the_catalog()
    print("ok")
