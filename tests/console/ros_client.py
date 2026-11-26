"""Deprecated: logic moved to src/agents/ppi_agent/src/client.py.

Console loads agent clients dynamically via tests/console/server.py.
Kept as a pointer so old imports fail loudly with a clear message.
"""

raise ImportError(
    "tests.console.ros_client is deprecated; "
    "use src/agents/ppi_agent/src/client.py (loaded by server.load_agent)"
)
