from aiogram.fsm.state import StatesGroup, State

class Search(StatesGroup):
    lang = State() 
    origin = State()
    destination = State()
    departure_date = State()
    return_date = State()
    adults = State()
    children = State()
    infants = State()
