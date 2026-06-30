from freemail_api.dns_policy import domain_dns_records
from freemail_api.dns_policy import verify_dns_posture


def test_domain_dns_records_include_mx_spf_dmarc_and_dkim():
    records = domain_dns_records(
        domain="example.com",
        hostname="freemail.example.com",
        dkim_keys=[{"dns_name": "mail._domainkey.example.com", "public_txt": "v=DKIM1; k=rsa; p=abc"}],
    )

    assert [record.type for record in records] == ["MX", "TXT", "TXT", "TXT"]
    assert records[0].value == "10 freemail.example.com."
    assert records[1].value == "v=spf1 mx -all"
    assert records[2].name == "_dmarc.example.com"
    assert records[3].name == "mail._domainkey.example.com"


def test_verify_dns_posture_accepts_matching_observed_records():
    expected = domain_dns_records(
        domain="example.com",
        hostname="freemail.example.com",
        dkim_keys=[{"dns_name": "mail._domainkey.example.com", "public_txt": "v=DKIM1; k=rsa; p=abc"}],
    )
    observed = [
        {"type": "MX", "name": "example.com.", "values": ["10 freemail.example.com."]},
        {"type": "TXT", "name": "example.com", "values": ["v=spf1 mx -all"]},
        {"type": "TXT", "name": "_dmarc.example.com", "values": ["v=DMARC1; p=quarantine; rua=mailto:postmaster@example.com"]},
        {"type": "TXT", "name": "mail._domainkey.example.com", "values": ["v=DKIM1; k=rsa; p=abc"]},
    ]

    posture = verify_dns_posture(domain="example.com", expected_records=expected, observed_records=observed)

    assert posture.ready is True
    assert all(check.found for check in posture.checks)


def test_verify_dns_posture_reports_missing_records():
    expected = domain_dns_records(domain="example.com", hostname="freemail.example.com", dkim_keys=[])
    observed = [{"type": "MX", "name": "example.com", "values": ["10 freemail.example.com."]}]

    posture = verify_dns_posture(domain="example.com", expected_records=expected, observed_records=observed)

    assert posture.ready is False
    assert [check.found for check in posture.checks] == [True, False, False]
