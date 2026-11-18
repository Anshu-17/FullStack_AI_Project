"""Fetching one page: every problem becomes an outcome, temporary problems are retried.

HTTP is faked with respx (no real network); DNS is faked with the fake_dns fixture.
"""
import httpx
import respx

from app.crawler.fetch import BACKOFF_CAP_SECONDS, fetch_page, make_client
from app.db.enums import PageOutcome

URL = "https://coop.example/about"


def fetch(url=URL):
    with make_client() as client:
        return fetch_page(client, url)


@respx.mock
def test_ok_page(fake_dns):
    respx.get(URL).respond(200, html="<html><title>About</title><p>Grain</p></html>")
    result = fetch()
    assert result.outcome == PageOutcome.OK
    assert result.http_status == 200
    assert "Grain" in result.html
    assert result.byte_size > 0


@respx.mock
def test_user_agent_is_sent(fake_dns):
    route = respx.get(URL).respond(200, html="<p>x</p>")
    fetch()
    assert route.calls.last.request.headers["user-agent"].startswith("BusinessEvidenceBot/")


@respx.mock
def test_redirect_to_private_address_is_blocked(fake_dns):
    respx.get(URL).respond(302, headers={"Location": "http://10.0.0.5/admin"})
    private = respx.get("http://10.0.0.5/admin").respond(200, html="<p>secret</p>")
    result = fetch()
    assert result.outcome == PageOutcome.BLOCKED_UNSAFE
    assert not private.called  # we never connected to the private address


@respx.mock
def test_safe_redirect_is_followed(fake_dns):
    respx.get(URL).respond(301, headers={"Location": "/about-us"})
    respx.get("https://coop.example/about-us").respond(200, html="<p>About us</p>")
    result = fetch()
    assert result.outcome == PageOutcome.OK
    assert result.final_url == "https://coop.example/about-us"


@respx.mock
def test_too_many_redirects(fake_dns):
    respx.get(URL).respond(302, headers={"Location": URL})  # redirects to itself forever
    result = fetch()
    assert result.outcome == PageOutcome.ERROR
    assert "redirects" in result.error_detail


@respx.mock
def test_404_is_http_error_without_retry(fake_dns, no_sleep):
    route = respx.get(URL).respond(404)
    result = fetch()
    assert result.outcome == PageOutcome.HTTP_ERROR
    assert result.http_status == 404
    assert route.call_count == 1
    assert no_sleep == []


@respx.mock
def test_503_then_200_is_retried_and_ok(fake_dns, no_sleep):
    route = respx.get(URL)
    route.side_effect = [httpx.Response(503), httpx.Response(200, html="<p>back</p>")]
    result = fetch()
    assert result.outcome == PageOutcome.OK
    assert route.call_count == 2
    assert len(no_sleep) == 1


@respx.mock
def test_retry_after_is_honoured_but_capped(fake_dns, no_sleep):
    route = respx.get(URL)
    route.side_effect = [httpx.Response(429, headers={"Retry-After": "120"}), httpx.Response(200, html="<p>ok</p>")]
    assert fetch().outcome == PageOutcome.OK
    assert no_sleep == [BACKOFF_CAP_SECONDS]  # asked for 120 s, we wait at most the cap


@respx.mock
def test_server_error_every_time_gives_up_after_retries(fake_dns, no_sleep):
    route = respx.get(URL).respond(500)
    result = fetch()
    assert result.outcome == PageOutcome.HTTP_ERROR
    assert route.call_count == 3  # 1 try + 2 retries


@respx.mock
def test_repeated_timeout_is_timeout(fake_dns, no_sleep):
    route = respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    result = fetch()
    assert result.outcome == PageOutcome.TIMEOUT
    assert route.call_count == 3
    assert all(0 < wait <= BACKOFF_CAP_SECONDS for wait in no_sleep)


@respx.mock
def test_image_is_not_html(fake_dns):
    respx.get(URL).respond(200, content=b"\x89PNG....", headers={"Content-Type": "image/png"})
    assert fetch().outcome == PageOutcome.NOT_HTML


@respx.mock
def test_oversized_body_is_too_large(fake_dns, crawler_settings):
    crawler_settings(crawl_max_page_bytes=1000)
    respx.get(URL).respond(200, html="<p>" + "x" * 5000 + "</p>")
    result = fetch()
    assert result.outcome == PageOutcome.TOO_LARGE
    assert result.html is None


@respx.mock
def test_oversized_body_without_content_length_is_cut_off_while_streaming(fake_dns, crawler_settings):
    crawler_settings(crawl_max_page_bytes=1000)

    def chunks():  # a streamed body: the server does not say how big it is
        for _ in range(10):
            yield b"x" * 500

    respx.get(URL).respond(200, headers={"Content-Type": "text/html"}, content=chunks())
    result = fetch()
    assert result.outcome == PageOutcome.TOO_LARGE
    assert result.byte_size <= 1500  # stopped soon after the limit, did not read all 5000 bytes


@respx.mock
def test_empty_body_is_empty(fake_dns):
    respx.get(URL).respond(200, html="   \n  ")
    assert fetch().outcome == PageOutcome.EMPTY


@respx.mock
def test_dns_failure_is_error(fake_dns):
    fake_dns["coop.example"] = None
    result = fetch()
    assert result.outcome == PageOutcome.ERROR
    assert "resolve" in result.error_detail


@respx.mock
def test_connection_refused_is_error(fake_dns, no_sleep):
    respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))
    assert fetch().outcome == PageOutcome.ERROR
