"""Unit tests for daemon helpers."""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from daemon import pick_port, port_free


def test_port_free_and_pick():
    # bind an ephemeral to discover a free pattern
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    # after close, should be free
    assert port_free(free)
    assert pick_port(free) == free
