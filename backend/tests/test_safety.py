"""SSRF protection: the crawler may only reach public web servers."""
import pytest

from app.crawler.safety import DNSResolutionError, UnsafeURLError, check_url_is_safe


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",                       # name resolving to loopback
        "http://10.0.0.5/",
        "http://192.168.1.1/admin",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata service
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",              # IPv4 loopback hidden inside IPv6
        "http://0.0.0.0/",
    ],
)
def test_private_and_local_addresses_are_blocked(fake_dns, url):
    fake_dns["localhost"] = ["127.0.0.1", "::1"]
    with pytest.raises(UnsafeURLError):
        check_url_is_safe(url)


@pytest.mark.parametrize("url", ["ftp://coop.example/", "file:///etc/passwd", "gopher://coop.example/", "http:///nohost"])
def test_bad_schemes_and_missing_host_are_blocked(fake_dns, url):
    with pytest.raises(UnsafeURLError):
        check_url_is_safe(url)


def test_credentials_in_url_are_blocked(fake_dns):
    with pytest.raises(UnsafeURLError):
        check_url_is_safe("http://user:pass@coop.example/")


def test_name_with_one_public_and_one_private_address_is_blocked(fake_dns):
    fake_dns["sneaky.example"] = ["93.184.216.34", "10.0.0.5"]
    with pytest.raises(UnsafeURLError):
        check_url_is_safe("https://sneaky.example/")


def test_public_address_is_allowed(fake_dns):
    fake_dns["coop.example"] = ["93.184.216.34"]
    check_url_is_safe("https://coop.example/about")  # no exception
    check_url_is_safe("http://93.184.216.34/")


def test_dns_failure_is_its_own_error(fake_dns):
    fake_dns["nowhere.example"] = None
    with pytest.raises(DNSResolutionError):
        check_url_is_safe("https://nowhere.example/")


def test_allowlist_works_in_development(fake_dns, crawler_settings):
    fake_dns["fixtures.localhost"] = ["127.0.0.1"]
    crawler_settings(environment="development", crawl_allowed_private_hosts="fixtures.localhost, other.local")
    check_url_is_safe("http://fixtures.localhost:8001/")  # allowed: explicitly listed


def test_allowlist_is_ignored_in_production(fake_dns, crawler_settings):
    fake_dns["fixtures.localhost"] = ["127.0.0.1"]
    crawler_settings(environment="production", crawl_allowed_private_hosts="fixtures.localhost")
    with pytest.raises(UnsafeURLError):
        check_url_is_safe("http://fixtures.localhost:8001/")
