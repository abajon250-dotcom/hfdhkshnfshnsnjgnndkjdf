from aiogram.fsm.state import State, StatesGroup

class WorkStates(StatesGroup):
    choosing_mode        = State()
    choosing_operator    = State()
    waiting_number       = State()
    waiting_qr_photo     = State()
    waiting_qr_number    = State()
    waiting_withdraw_amt = State()

class AdminStates(StatesGroup):
    waiting_broadcast     = State()
    waiting_price         = State()
    waiting_reject_reason = State()