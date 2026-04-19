
from aiogram.fsm.state import State, StatesGroup


class SetupStates(StatesGroup):
    waiting_for_otp = State()
    waiting_for_restore_choice = State()
    waiting_for_database_channel = State()


class AddPairStates(StatesGroup):
    waiting_for_pair_number = State()
    waiting_for_source = State()
    waiting_for_scan_amount = State()
    waiting_for_target = State()
    waiting_for_ads = State()
    waiting_for_confirm = State()


class DeletePairStates(StatesGroup):
    waiting_for_pair_number = State()
    waiting_for_confirm = State()


class EditSourceStates(StatesGroup):
    waiting_for_pair_number = State()
    waiting_for_source = State()
    waiting_for_scan_amount = State()
    waiting_for_confirm = State()


class EditTargetStates(StatesGroup):
    waiting_for_pair_number = State()
    waiting_for_target = State()
    waiting_for_confirm = State()


class KeywordStates(StatesGroup):
    waiting_for_pair_selection = State()
    waiting_for_add_keywords = State()
    waiting_for_clear_keywords = State()


class AdsStates(StatesGroup):
    waiting_for_pair_number_add = State()
    waiting_for_ads_links = State()
    waiting_for_pair_number_delete = State()


class CheckStates(StatesGroup):
    waiting_for_pair_or_all = State()
