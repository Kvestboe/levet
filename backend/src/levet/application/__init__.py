"""Application layer: use cases and the ports they depend on.

Depends on the domain only. Everything that touches the outside world
(database, files, PDF rendering, background jobs) is reached through a port
defined in ``ports`` and implemented under ``levet.adapters``.
"""
