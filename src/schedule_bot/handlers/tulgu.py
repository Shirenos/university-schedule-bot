"""TulSU timetable sync: /tulgu, /sync and /filters (choice of parallel subgroups)."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from schedule_bot.config import Settings
from schedule_bot.db import Database
from schedule_bot.handlers.keyboards import filter_keyboard
from schedule_bot.models import TulguSettings
from schedule_bot.services.filters import ALL, VariantGroup
from schedule_bot.services.reminders import ReminderScheduler
from schedule_bot.services.sync import SyncResult, SyncService
from schedule_bot.services.tulgu import TulguError, is_valid_group

router = Router(name="tulgu")

USAGE = (
    "🏛 <b>Расписание ТулГУ</b>\n━━━━━━━━━━━━━━━\n\n"
    "Укажите номер группы, например: <code>/tulgu 221461</code> — я загружу расписание "
    "с сайта tulsu.ru и буду показывать его в /today, /tomorrow, /week и /next.\n"
    "Обновить данные позже — /sync."
)
CACHE_NOTE = "Данные взяты из кэша: сайт опрашивается не чаще раза в 5 минут."


def _describe(tulgu: TulguSettings, settings: Settings, count: int | None = None) -> str:
    lines = [f"👥 Группа: <b>{escape(tulgu.group)}</b>"]
    if count is not None:
        lines.append(f"📚 Занятий загружено: <b>{count}</b>")
    if tulgu.min_date and tulgu.max_date:
        lines.append(f"📆 Период: {tulgu.min_date:%d.%m.%Y} – {tulgu.max_date:%d.%m.%Y}")
    if tulgu.synced_at:
        local = tulgu.synced_at.astimezone(settings.timezone)
        lines.append(f"🕘 Обновлено: {local:%d.%m.%Y %H:%M}")
    return "\n".join(lines)


def _prompt_text(group: VariantGroup) -> str:
    return (
        f"🔀 <b>{escape(group.subject)}</b> — {escape(group.kind or 'занятия')}\n"
        "В одно и то же время идут параллельные подгруппы. Какую показывать?"
    )


async def send_filter_prompts(message: Message, groups: list[VariantGroup]) -> None:
    for group in groups:
        await message.answer(_prompt_text(group), reply_markup=filter_keyboard(group))


async def sync_and_report(
    message: Message,
    user_id: int,
    group: str,
    db: Database,
    settings: Settings,
    sync_service: SyncService,
    scheduler: ReminderScheduler,
) -> None:
    await message.answer(f"⏳ Загружаю расписание группы {escape(group)}…")
    try:
        result: SyncResult = await sync_service.sync(user_id, group)
    except TulguError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    scheduler.reschedule(user_id)
    text = "✅ Расписание загружено.\n\n" + _describe(result.settings, settings, result.lessons)
    if result.from_cache:
        text += f"\n\n{CACHE_NOTE}"
    await message.answer(text)
    if result.pending:
        await message.answer(
            "Нашёл параллельные подгруппы (например, иностранный язык). "
            "Выберите свою — изменить выбор можно позже через /filters."
        )
        await send_filter_prompts(message, result.pending)


async def show_status(message: Message, user_id: int, db: Database, settings: Settings) -> None:
    """Saved group, number of lessons and last sync time (or the usage hint)."""
    tulgu = await db.get_tulgu(user_id)
    if tulgu is None:
        await message.answer(USAGE)
        return
    count = await db.count_dated_lessons(user_id)
    await message.answer(
        "🏛 <b>Расписание ТулГУ</b>\n━━━━━━━━━━━━━━━\n\n"
        + _describe(tulgu, settings, count)
        + "\n\n🔄 Обновить — /sync\n🔀 Подгруппы — /filters\n"
        "🔁 Другая группа — <code>/tulgu НОМЕР</code>"
    )


async def run_sync(
    message: Message,
    user_id: int,
    db: Database,
    settings: Settings,
    sync_service: SyncService,
    scheduler: ReminderScheduler,
) -> None:
    """Re-sync the user's saved group (shared by /sync and the settings menu)."""
    tulgu = await db.get_tulgu(user_id)
    if tulgu is None:
        await message.answer("Группа не выбрана.\n\n" + USAGE)
        return
    await sync_and_report(message, user_id, tulgu.group, db, settings, sync_service, scheduler)


async def show_filters(
    message: Message, user_id: int, db: Database, sync_service: SyncService
) -> None:
    """Current subgroup choices and keyboards to change them."""
    if await db.get_tulgu(user_id) is None:
        await message.answer("Сначала подключите расписание: <code>/tulgu НОМЕР_ГРУППЫ</code>.")
        return
    groups = await sync_service.variant_groups(user_id)
    if not groups:
        await message.answer("В вашем расписании нет параллельных подгрупп — фильтры не нужны.")
        return
    choices = await db.get_filters(user_id)
    lines = ["🔀 <b>Параллельные подгруппы</b>", "━━━━━━━━━━━━━━━", ""]
    for group in groups:
        choice = choices.get(group.key)
        shown = "не выбрано" if choice is None else ("все" if choice == ALL else choice)
        lines.append(f"• {escape(group.subject)} ({escape(group.kind)}): <b>{escape(shown)}</b>")
    await message.answer("\n".join(lines) + "\n\nВыберите заново:")
    await send_filter_prompts(message, groups)


@router.message(Command("tulgu"))
async def cmd_tulgu(
    message: Message,
    command: CommandObject,
    db: Database,
    settings: Settings,
    sync_service: SyncService,
    scheduler: ReminderScheduler,
) -> None:
    assert message.from_user
    arg = (command.args or "").strip()
    if not arg:
        await show_status(message, message.from_user.id, db, settings)
        return
    if not is_valid_group(arg):
        await message.answer("⚠️ Некорректный номер группы.\n\n" + USAGE)
        return
    await sync_and_report(message, message.from_user.id, arg, db, settings, sync_service, scheduler)


@router.message(Command("sync"))
async def cmd_sync(
    message: Message,
    db: Database,
    settings: Settings,
    sync_service: SyncService,
    scheduler: ReminderScheduler,
) -> None:
    assert message.from_user
    await run_sync(message, message.from_user.id, db, settings, sync_service, scheduler)


@router.message(Command("filters"))
async def cmd_filters(message: Message, db: Database, sync_service: SyncService) -> None:
    assert message.from_user
    await show_filters(message, message.from_user.id, db, sync_service)


@router.callback_query(F.data.startswith("flt:"))
async def on_filter_choice(
    callback: CallbackQuery,
    db: Database,
    sync_service: SyncService,
    scheduler: ReminderScheduler,
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, token, option = parts
    user_id = callback.from_user.id
    group = next((g for g in await sync_service.variant_groups(user_id) if g.token == token), None)
    if group is None:
        await callback.answer("Эти данные устарели. Откройте /filters заново.", show_alert=True)
        return
    if option == "a":
        choice = ALL
    elif option.isdigit() and int(option) < len(group.options):
        choice = group.options[int(option)]
    else:
        await callback.answer()
        return
    await db.set_filter(user_id, group.subject, group.kind, choice)
    scheduler.reschedule(user_id)
    await callback.answer("Сохранено")
    if isinstance(callback.message, Message):
        verdict = "показываю все варианты" if choice == ALL else f"оставляю «{escape(choice)}»"
        await callback.message.edit_text(
            f"✅ <b>{escape(group.subject)}</b> — {escape(group.kind)}: {verdict}.",
            reply_markup=None,
        )
