#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Single source of truth for the project version.

This module intentionally has NO imports so it can be read statically by
the build backend (pyproject.toml -> tool.setuptools.dynamic) and by the
C++ build, keeping every component in sync automatically.
"""

__version__ = "1.1.3"
