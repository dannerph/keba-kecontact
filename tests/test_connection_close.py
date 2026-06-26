"""Tests for KebaKeContact.close()."""

import asyncio
from unittest.mock import MagicMock

import pytest

from keba_kecontact.connection import KebaKeContact


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the Singleton between tests so each gets a fresh instance."""
    KebaKeContact._instance = None
    yield
    KebaKeContact._instance = None


@pytest.fixture
def keba():
    loop = asyncio.new_event_loop()
    return KebaKeContact(loop=loop, timeout=3)


def _mock_station():
    station = MagicMock()
    station.stop_periodic_request = MagicMock()
    return station


def test_close_stops_all_charging_stations(keba):
    """close() calls stop_periodic_request() on every registered station."""
    s1, s2 = _mock_station(), _mock_station()
    keba._charging_stations = {"192.168.1.1": s1, "192.168.1.2": s2}
    keba._stream = MagicMock()

    keba.close()

    s1.stop_periodic_request.assert_called_once()
    s2.stop_periodic_request.assert_called_once()


def test_close_clears_charging_stations(keba):
    """close() empties the charging stations registry."""
    keba._charging_stations = {"192.168.1.1": _mock_station()}
    keba._stream = MagicMock()

    keba.close()

    assert keba._charging_stations == {}


def test_close_closes_stream_and_sets_none(keba):
    """close() calls close() on the stream and sets _stream to None."""
    mock_stream = MagicMock()
    keba._stream = mock_stream

    keba.close()

    mock_stream.close.assert_called_once()
    assert keba._stream is None


def test_close_without_stream_does_not_raise(keba):
    """close() is a no-op for the stream when _stream is already None."""
    keba._stream = None

    keba.close()

    assert keba._stream is None


def test_close_allows_socket_reinit(keba):
    """After close(), _stream is None so init_socket() will rebind on next call."""
    keba._stream = MagicMock()

    keba.close()

    assert keba._stream is None
