# pylint: disable=too-few-public-methods  # Module defining command classes for the allocation domain. Contains base Command class and dataclass implementations for Allocate, CreateBatch, ChangeBatchQuantity, and Deallocate commands to handle domain operations.
from datetime import date
from typing import Optional
from dataclasses import dataclass


class Command:
    pass


@dataclass
class Allocate(Command):
    orderid: str
    sku: str
    qty: int


@dataclass
class CreateBatch(Command):
    ref: str
    sku: str
    qty: int
    eta: Optional[date] = None


@dataclass
class ChangeBatchQuantity(Command):
    ref: str
    qty: int


@dataclass
class Deallocate(Command):
    orderid: str
    sku: str
    qty: int
