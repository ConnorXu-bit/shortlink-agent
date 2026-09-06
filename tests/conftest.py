"""共享 fixtures：FakeRedis 与注入到工具箱的短链接存储。"""

import fakeredis
import pytest

from tools import ShortLinkToolbox


@pytest.fixture
def redis_client():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    client.flushall()


@pytest.fixture
def toolbox(redis_client):
    return ShortLinkToolbox(redis_client)
