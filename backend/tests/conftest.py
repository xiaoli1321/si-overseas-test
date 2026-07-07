import asyncio
import pytest
import pytest_asyncio
from src.core.database import engine

@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def dispose_engine_after_each_test():
    yield
    await engine.dispose()
