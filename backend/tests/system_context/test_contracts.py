import pytest
from pydantic import ValidationError

from holospan_api.domains.system_context.contracts import CreateSystemRequest


def valid_payload() -> dict[str, str]:
    return {
        "displayName": "Claims Copilot",
        "slug": "claims-copilot",
        "description": "Assists claims reviewers.",
        "systemType": "agent",
        "lifecycleStage": "development",
    }


def test_ac9_accepts_the_documented_create_contract() -> None:
    request = CreateSystemRequest.model_validate(valid_payload())

    assert request.display_name == "Claims Copilot"
    assert request.slug == "claims-copilot"
    assert request.system_type.value == "agent"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("displayName", "x"),
        ("slug", "Claims Copilot"),
        ("slug", "ab"),
        ("description", "x" * 2001),
        ("systemType", "assistant"),
        ("lifecycleStage", "local"),
    ],
)
def test_ac9_rejects_values_outside_the_contract(field: str, value: str) -> None:
    payload = valid_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        CreateSystemRequest.model_validate(payload)
