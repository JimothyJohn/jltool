"""Shared fixtures and fakes for jltool tests.

The strategy: never instantiate the real `jarvislabs.Client`. Instead, the
`mock_client` fixture replaces `jltool.cli.Client` with a factory that returns
a `MagicMock` exposing the same `account / instances / scripts / filesystems /
ssh_keys` namespaces. Tests configure `mock_client.<namespace>.<method>.return_value`
or `.side_effect` and assert on stdout/stderr/exit_code from the CliRunner result.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from jltool import cli


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class Fake:
    """Generic attribute bag mimicking a pydantic-ish SDK model."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)

    def model_dump(self) -> dict:
        return dict(self.__dict__)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Fake({self.__dict__!r})"


def fake_instance(**overrides: Any) -> Fake:
    base = dict(
        machine_id=42,
        name="test-instance",
        status="Running",
        gpu_type="A100",
        num_gpus=1,
        storage_gb=40,
        template="pytorch",
        url="https://lab.jarvislabs.net/42",
        ssh_command="ssh -p 1234 user@1.2.3.4",
        public_ip="1.2.3.4",
        region="IN2",
        fs_id=None,
        cost=0.0,
    )
    base.update(overrides)
    return Fake(**base)


def fake_script(**overrides: Any) -> Fake:
    base = dict(script_id=7, script_name="deps")
    base.update(overrides)
    return Fake(**base)


def fake_fs(**overrides: Any) -> Fake:
    base = dict(fs_id=3, fs_name="data", storage=200)
    base.update(overrides)
    return Fake(**base)


def fake_key(**overrides: Any) -> Fake:
    base = dict(key_id=11, key_name="laptop")
    base.update(overrides)
    return Fake(**base)


def fake_gpu(**overrides: Any) -> Fake:
    base = dict(gpu_type="A100", num_free_devices=4, price_per_hour=1.29, region="IN2")
    base.update(overrides)
    return Fake(**base)


def fake_template(**overrides: Any) -> Fake:
    base = dict(id=1, title="PyTorch", category="ML")
    base.update(overrides)
    return Fake(**base)


def fake_user_info(**overrides: Any) -> Fake:
    base = dict(
        user_id="u-123",
        name="Test User",
        address1="1 Test St",
        address2="",
        city="Testville",
        country="US",
        phone_number="555-0100",
        state="CA",
        zip_code="94000",
        tax_id="",
    )
    base.update(overrides)
    return Fake(**base)


def fake_balance(balance: float = 10.0, grants: float = 0.0) -> Fake:
    return Fake(balance=balance, grants=grants)


def fake_metrics(**overrides: Any) -> Fake:
    base = dict(
        running_instances=0,
        paused_instances=0,
        running_vms=0,
        paused_vms=0,
        deployments=0,
        filesystems=0,
    )
    base.update(overrides)
    return Fake(**base)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    """Typer CliRunner — stdout and stderr are captured separately by default
    in modern click (>=8.2)."""
    return CliRunner()


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch `jltool.cli.Client` so the real SDK is never invoked."""
    client = MagicMock(name="JarvislabsClient")

    # Configure currency to return a real string by default (it's used in
    # account_balance even when balance is mocked).
    client.account.currency.return_value = "USD"

    class FakeClientFactory:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._client = client

        def __enter__(self) -> MagicMock:
            return self._client

        def __exit__(self, *args: Any) -> bool:
            return False

    monkeypatch.setattr(cli, "Client", FakeClientFactory)
    return client


@pytest.fixture(autouse=True)
def reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset module-level state and clear JL_DEFAULT_* env between tests."""
    cli._state.json = False
    for key in list(os.environ.keys()):
        if key.startswith("JL_DEFAULT_"):
            monkeypatch.delenv(key, raising=False)
    yield
    cli._state.json = False
