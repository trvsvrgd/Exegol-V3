from scripts.release_ports import parse_netstat_listeners


def test_parse_netstat_listeners_handles_ipv4_and_ipv6_addresses():
    output = """
  TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       1111
  TCP    [::1]:3000             [::]:0                 LISTENING       2222
  TCP    [::1]:3000             [::1]:49316            ESTABLISHED     3333
"""

    assert parse_netstat_listeners(output, [8000, 3000]) == {1111, 2222}
