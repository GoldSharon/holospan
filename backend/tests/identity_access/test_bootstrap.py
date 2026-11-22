from holospan_api.domains.identity_access.bootstrap import BootstrapAllowlist


def test_ac9_bootstrap_requires_exact_issuer_and_subject() -> None:
    allowlist = BootstrapAllowlist.parse("https://id.example|admin-123")

    assert allowlist.matches("https://id.example", "admin-123")
    assert not allowlist.matches("https://other.example", "admin-123")
    assert not allowlist.matches("https://id.example", "admin-124")
    assert not allowlist.matches("https://id.example.evil", "admin-123")
