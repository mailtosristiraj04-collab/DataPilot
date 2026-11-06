from uuid import uuid4

from app.core.security import Principal, require_owner
from app.db.models import Dataset


def test_development_principal_is_required_for_owner_checks() -> None:
    principal = Principal("owner-a")
    require_owner("owner-a", principal)


def test_owner_check_does_not_accept_a_session_identifier() -> None:
    principal = Principal("owner-a")

    try:
        require_owner(str(uuid4()), principal)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("an unrelated session identifier must not authorize access")


def test_dataset_model_contains_explicit_owner() -> None:
    assert Dataset.owner_id.property.columns[0].nullable is False
