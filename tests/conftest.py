# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))


import pytest


@pytest.fixture(autouse=True, scope="session")
def _cleanup_db_engines():
    """Dispose SQLAlchemy engines after the test session to avoid hangs."""
    yield

    from db import session as session_mod

    # Dispose the cached sync engine (created by @lru_cache get_sessionmaker)
    if session_mod.get_sessionmaker.cache_info().currsize:
        factory = session_mod.get_sessionmaker()
        engine = factory.kw.get("bind")
        if engine is not None:
            engine.dispose()
        session_mod.get_sessionmaker.cache_clear()

    # Dispose the async engine singleton
    if session_mod._async_sessionmaker_instance is not None:
        import asyncio

        engine = session_mod._async_sessionmaker_instance.kw.get("bind")
        if engine is not None:
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                engine.dispose()
            )
        session_mod._async_sessionmaker_instance = None
