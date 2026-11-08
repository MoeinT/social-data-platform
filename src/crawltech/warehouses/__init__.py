"""Analytical warehouse ports and local implementation."""

from crawltech.warehouses.interfaces import Warehouse
from crawltech.warehouses.local import LocalWarehouse

__all__ = ["LocalWarehouse", "Warehouse"]
