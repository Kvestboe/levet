"""ASGI entry point.

uvicorn levet.main:create_app --factory
"""

import logging

from fastapi import FastAPI

from levet.adapters.http.app import create_app as create_http_app
from levet.bootstrap import build_container
from levet.config import Settings


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return create_http_app(build_container(Settings.from_env()))
