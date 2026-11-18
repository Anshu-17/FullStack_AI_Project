"""SSRF protection: only let the crawler talk to PUBLIC websites.

SSRF = Server-Side Request Forgery. A user uploads a "company website" that
actually points at something private - our own database (127.0.0.1), the office
network (10.x / 192.168.x) or the cloud metadata service (169.254.169.254) that
hands out credentials. Every URL is checked here BEFORE we connect, and again
on every redirect hop (see fetch.py).

Known limitation (DNS rebinding): we resolve the name here, then httpx resolves
it again when it connects. A hostile DNS server could answer "public" to us and
"private" to httpx a moment later. Re-checking every redirect hop narrows this
window; fully closing it means pinning the checked IP for the connection
(future work).
"""
import ipaddress
import socket
from urllib.parse import urlsplit

from app.config import settings

ALLOWED_SCHEMES = {"http", "https"}


class UnsafeURLError(Exception):
    """The URL must not be fetched (bad scheme, credentials, private address, ...)."""


class DNSResolutionError(Exception):
    """The hostname could not be resolved (does not exist, or DNS is down)."""


def allowed_private_hosts() -> set[str]:
    """Hostnames allowed to resolve to private IPs - for local test fixtures only.

    Always empty in production, whatever the setting says.
    """
    if settings.environment == "production":
        return set()
    return {h.strip().lower() for h in settings.crawl_allowed_private_hosts.split(",") if h.strip()}


def is_allowlisted(host: str) -> bool:
    """Exact name ('fixtures.localhost') or a '*.suffix' pattern ('*.fixture.test' matches 'a.fixture.test')."""
    for entry in allowed_private_hosts():
        if host == entry or (entry.startswith("*.") and host.endswith(entry[1:])):
            return True
    return False


def is_ip_literal(host: str) -> bool:
    """True for '10.0.0.5' or '::1' (an address typed directly, no DNS needed)."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def resolve_host(host: str) -> list[str]:
    """All IP addresses a hostname resolves to (IPv4 and IPv6)."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise DNSResolutionError(f"could not resolve {host}") from exc
    # Each info is (family, type, proto, canonname, sockaddr); sockaddr[0] is the IP.
    return sorted({info[4][0] for info in infos})


def is_public_ip(ip_text: str) -> bool:
    """True only for globally routable addresses.

    `is_global` is False for loopback (127.x, ::1), private (10.x, 172.16-31.x,
    192.168.x), link-local (169.254.x - cloud metadata), carrier NAT, reserved, ...
    """
    ip = ipaddress.ip_address(ip_text.split("%", 1)[0])  # drop an IPv6 zone id like "fe80::1%eth0"
    # "::ffff:127.0.0.1" is IPv4 127.0.0.1 written as IPv6 - judge the IPv4 address inside.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url_is_safe(url: str) -> None:
    """Raise UnsafeURLError (or DNSResolutionError) unless `url` points at a public web server."""
    parts = urlsplit(url)

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme '{parts.scheme}' not allowed (only http/https)")

    host = (parts.hostname or "").lower()
    if not host:
        raise UnsafeURLError("URL has no hostname")

    # "http://user:pass@host/" - never send credentials, and this form is a classic trick
    # to make a URL look like it goes somewhere else.
    if parts.username is not None or parts.password is not None:
        raise UnsafeURLError("URLs with user:password@ are not allowed")

    try:
        parts.port  # noqa: B018 - accessing .port validates it (raises ValueError if bad)
    except ValueError as exc:
        raise UnsafeURLError("invalid port") from exc

    if is_allowlisted(host):
        return  # local fixture explicitly allowed (never in production)

    ips = [host] if is_ip_literal(host) else resolve_host(host)
    # EVERY address must be public: a name resolving to one public and one private
    # address could otherwise be used to reach the private one.
    for ip in ips:
        if not is_public_ip(ip):
            raise UnsafeURLError(f"{host} resolves to non-public address {ip}")
