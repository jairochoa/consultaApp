import pytest

from consultorio.config import load_config
from consultorio.domain.rules import DomainError, validate_cedula, validate_resultado_editable


def test_validate_cedula_only_numbers():
    validate_cedula("12345678")
    with pytest.raises(DomainError):
        validate_cedula("12A345")


def test_result_only_when_received():
    cfg = load_config()
    with pytest.raises(DomainError):
        validate_resultado_editable(cfg, "enviado", "ABC")
    validate_resultado_editable(cfg, "recibido", "ABC")
