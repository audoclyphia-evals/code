# pylint: disable=broad-except  # Module that defines the MessageBus class for dispatching commands and events in the allocation service layer. It imports domain-specific commands and events, defines a Message type alias for Command and Event objects, sets up logging, and includes a type hint for unit_of_work. The MessageBus class is designed to handle message processing with transactional consistency.
from __future__ import annotations
import logging
from typing import Callable, Dict, List, Union, Type, TYPE_CHECKING
from allocation.domain import commands, events

if TYPE_CHECKING:
    from . import unit_of_work

logger = logging.getLogger(__name__)

Message = Union[commands.Command, events.Event]


class MessageBus:
    def __init__(
        """Initializes the MessageBus with a unit of work, event handlers dictionary (mapping event types to handler callables), command handlers dictionary (mapping command types to handler callables), and an empty message queue. This method sets up the bus to manage command and event dispatching, using the unit of work for transactional state management, and prepares for message queuing during processing."""
        self,
        uow: unit_of_work.AbstractUnitOfWork,
        event_handlers: Dict[Type[events.Event], List[Callable]],
        command_handlers: Dict[Type[commands.Command], Callable],
    ):
        self.uow = uow
        self.event_handlers = event_handlers
        self.command_handlers = command_handlers
        self.queue = []  # type: List[Message]

    def handle(self, message: Message):
        self.queue = [message]
        while self.queue:
            message = self.queue.pop(0)
            if isinstance(message, events.Event):
                self.handle_event(message)
            elif isinstance(message, commands.Command):
                self.handle_command(message)
            else:
                raise Exception(f"{message} was not an Event or Command")

    def handle_event(self, event: events.Event):
        for handler in self.event_handlers[type(event)]:
            try:
                logger.debug("handling event %s with handler %s", event, handler)
                handler(event)
                self.queue.extend(self.uow.collect_new_events())
            except Exception:
                logger.exception("Exception handling event %s", event)
                continue

    def handle_command(self, command: commands.Command):
        logger.debug("handling command %s", command)
        try:
            handler = self.command_handlers[type(command)]
            handler(command)
            self.queue.extend(self.uow.collect_new_events())
        except Exception:
            logger.exception("Exception handling command %s", command)
            raise
