import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from fairshift.api import app  # noqa: E402

client = TestClient(app)


def test_app_page_and_demo():
    assert "fairshift" in client.get("/").text
    assert "Kopi" in client.get("/api/demo").json()["yaml"]


def test_solve_then_two_sick_calls_compound():
    text = client.get("/api/demo").json()["yaml"]
    first = client.post("/api/solve", json={"yaml": text}).json()
    assert first["totals"]["status"] == "OPTIMAL" and "<table>" in first["rota_html"]
    one = client.post("/api/replan", json={"yaml": text, "assignments": first["assignments"],
                                           "absent": "farid", "from": "2026-10-15"}).json()
    assert "farid" in one["yaml"] and "2026-10-15" in one["yaml"]
    # the second sick call starts from the YAML the first returned: Farid stays off
    two = client.post("/api/replan", json={"yaml": one["yaml"], "assignments": one["assignments"],
                                           "absent": "grace", "from": "2026-10-16"}).json()
    assert not any(s == "farid" and k >= "2026-10-15" for s, k in two["assignments"])
    assert not any(s == "grace" and k >= "2026-10-16" for s, k in two["assignments"])


@pytest.mark.parametrize("text", ["not: [valid", "- just a list", "start: 2026-10-12\nstaff: []"])
def test_bad_input_is_a_422_with_a_reason(text):
    r = client.post("/api/solve", json={"yaml": text})
    assert r.status_code == 422 and r.json()["detail"]
