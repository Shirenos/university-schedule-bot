"""aiogram routers."""

from __future__ import annotations

from aiogram import Router

from schedule_bot.handlers import add, basic, importer, manage, menu, remind, tulgu, view


def build_router() -> Router:
    """Assemble the root router.

    Order matters: plain command handlers come first so that commands such as ``/today``
    keep working while a dialog (``/add``, ``/import``) is in progress; the FSM step
    handlers, which accept free text, are registered last.
    """
    root = Router(name="root")
    root.include_routers(
        basic.router,
        menu.router,
        view.router,
        manage.router,
        remind.router,
        tulgu.router,
        add.router,
        importer.router,
    )
    return root
