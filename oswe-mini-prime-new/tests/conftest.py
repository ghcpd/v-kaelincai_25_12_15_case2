import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from httpx import AsyncClient, ASGITransport
from src.app import app as appointment_app
from mocks.legacy_mock import app as legacy_app
from asgi_lifespan import LifespanManager

@pytest.fixture
async def appointment_client():
    transport = ASGITransport(app=appointment_app)
    async with LifespanManager(appointment_app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

@pytest.fixture
async def legacy_client():
    transport = ASGITransport(app=legacy_app)
    async with LifespanManager(legacy_app):
        async with AsyncClient(transport=transport, base_url="http://legacy") as ac:
            yield ac
