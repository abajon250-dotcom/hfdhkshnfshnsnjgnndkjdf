from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from states import WorkStates
from database import get_user, add_balance
from cryptobot import create_check
from config import MIN_WITHDRAW

router = Router()

@router.callback_query(F.data == "withdraw")
async def withdraw(cb: CallbackQuery, state: FSMContext):
    u = await get_user(cb.from_user.id)
    if u["balance"] < MIN_WITHDRAW:
        return await cb.answer(f"❌ Минимум для вывода: ${MIN_WITHDRAW:.2f}\nБаланс: ${u['balance']:.2f}", show_alert=True)
    await state.set_state(WorkStates.waiting_withdraw_amt)
    await cb.message.answer(f"💸 Введи сумму вывода (мин. ${MIN_WITHDRAW:.2f}):\nДоступно: <b>${u['balance']:.2f}</b>")
    await cb.answer()

@router.message(WorkStates.waiting_withdraw_amt, F.text)
async def do_withdraw(msg: Message, state: FSMContext):
    try: amount = round(float(msg.text.replace(",", ".")), 2)
    except: return await msg.answer("❗ Введи число.")

    u = await get_user(msg.from_user.id)
    if amount < MIN_WITHDRAW or amount > u["balance"]:
        return await msg.answer("❗ Некорректная сумма.")

    try: link = await create_check(amount, msg.from_user.id)
    except Exception as e: return await msg.answer(f"⚠️ Ошибка CryptoBot: {e}")

    await add_balance(msg.from_user.id, -amount)
    await state.clear()
    await msg.answer(f"✅ Чек на <b>${amount:.2f}</b> создан:\n{link}")