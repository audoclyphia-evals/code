from __future__ import annotations
import functools
from dataclasses import dataclass
from datetime import date
from typing import Optional, List, Set
from . import commands, events


class Product:
    def __init__(self, sku: str, batches: List[Batch], version_number: int = 0):
        self.sku = sku
        self.batches = batches
        self.version_number = version_number
        self.events = []  # type: List[events.Event]

    def allocate(self, line: OrderLine) -> str:
        try:
            batch = next(b for b in sorted(self.batches) if b.can_allocate(line))
            batch.allocate(line)
            self.version_number += 1
            self.events.append(
                events.Allocated(
                    orderid=line.orderid,
                    sku=line.sku,
                    qty=line.qty,
                    batchref=batch.reference,
                )
            )
            return batch.reference
        except StopIteration:
            self.events.append(events.OutOfStock(line.sku))
            return None

    def change_batch_quantity(self, ref: str, qty: int):
        batch = next(b for b in self.batches if b.reference == ref)
        batch._purchased_quantity = qty
        while batch.available_quantity < 0:
            line = batch.deallocate_one()
            self.events.append(events.Deallocated(line.orderid, line.sku, line.qty))

    def deallocate(self, line: OrderLine):
        """Deallocates an order line from the product's batch by locating a batch that can deallocate it, removing the allocation, incrementing the product's version number, and emitting a Deallocated event. Raises ValueError if no batch can accommodate the deallocation for the given order line."""
        batch = next(
            (b for b in self.batches if b.can_deallocate(line)),
            None,
        )
        if batch is None:
            raise ValueError(
                f"Cannot deallocate: no batch found with an allocation for "
                f"order '{line.orderid}', sku '{line.sku}'"
            )
        batch.deallocate(line)
        self.version_number += 1
        self.events.append(events.Deallocated(line.orderid, line.sku, line.qty))


@dataclass(unsafe_hash=True)
class OrderLine:
    orderid: str
    sku: str
    qty: int


@functools.total_ordering
class Batch:
    def __init__(self, ref: str, sku: str, qty: int, eta: Optional[date]):
        self.reference = ref
        self.sku = sku
        self.eta = eta
        self._purchased_quantity = qty
        self._allocations = set()  # type: Set[OrderLine]

    def __repr__(self):
        return f"<Batch {self.reference}>"

    def __eq__(self, other):
        if not isinstance(other, Batch):
            return False
        return other.reference == self.reference

    def __hash__(self):
        return hash(self.reference)

    def __gt__(self, other):
        if self.eta is None:
            return False
        if other.eta is None:
            return True
        return self.eta > other.eta

    def allocate(self, line: OrderLine):
        if self.can_allocate(line):
            self._allocations.add(line)

    def deallocate(self, line: OrderLine):
        """Removes the specified order line from the batch's allocation set if it is currently allocated; this operation is idempotent and does nothing if the line is not present."""
        if line in self._allocations:
            self._allocations.discard(line)

    def can_deallocate(self, line: OrderLine) -> bool:
        """Checks if the given order line is allocated in this batch, returning True if it can be deallocated (i.e., is in the allocations), False otherwise."""
        return line in self._allocations

    def deallocate_one(self) -> OrderLine:
        return self._allocations.pop()

    @property
    def allocated_quantity(self) -> int:
        return sum(line.qty for line in self._allocations)

    @property
    def available_quantity(self) -> int:
        return self._purchased_quantity - self.allocated_quantity

    def can_allocate(self, line: OrderLine) -> bool:
        return self.sku == line.sku and self.available_quantity >= line.qty
