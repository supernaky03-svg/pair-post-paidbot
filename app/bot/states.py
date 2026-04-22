from aiogram.fsm.state import State, StatesGroup


class OtpStates(StatesGroup):
    waiting_otp = State()
    waiting_restore_choice = State()


class AddPairStates(StatesGroup):
    waiting_pair_no = State()
    waiting_source = State()
    waiting_scan = State()
    waiting_target = State()
    waiting_ads = State()
    waiting_post_rule = State()
    waiting_forward_rule = State()
    waiting_remove_url_rule = State()
    waiting_confirm = State()


class DeletePairStates(StatesGroup):
    waiting_pair_no = State()
    waiting_confirm = State()


class EditSourceStates(StatesGroup):
    waiting_pair_no = State()
    waiting_source = State()
    waiting_scan = State()
    waiting_remove_url_rule = State()
    waiting_confirm = State()


class EditTargetStates(StatesGroup):
    waiting_pair_no = State()
    waiting_target = State()
    waiting_confirm = State()


class KeywordStates(StatesGroup):
    waiting_pair = State()
    waiting_action = State()
    waiting_add_values = State()
    waiting_clear_values = State()


class AdsStates(StatesGroup):
    waiting_action = State()
    waiting_pair_for_add = State()
    waiting_pair_for_delete = State()
    waiting_values = State()
    waiting_delete_confirm = State()


class RuleStates(StatesGroup):
    waiting_pair = State()
    waiting_value = State()


class CheckStates(StatesGroup):
    waiting_pair = State()
    
