from inspect import isclass
from pkgutil import iter_modules,extend_path
from pathlib import Path
from importlib import import_module

from .my_decks_manager import *
from .my_decks import *
from .my_decks_app_base import *
from .window_check_base import *

# iterate through the modules in the current package
package_dir = extend_path(__path__, __name__)

for item in iter_modules(package_dir):
    module_name = item.name
    if module_name in ["my_decks_manager", "my_decks", "base_app", "window_check_base"]:
        continue
    # import the module and iterate through its attributes
    module = import_module(f"{__name__}.{module_name}")
    for attribute_name in dir(module):
        attribute = getattr(module, attribute_name)

        if isclass(attribute):
            # Add the class to this package's variables
            globals()[attribute_name] = attribute

# for mypy: cannot use dynamic loading with mypy
from .app_alert import *
from .app_calendar import *
from .app_clock import *
from .game_memory import *
from .game_random_number import *
from .game_tic_tack_toe import *
from .game_whac_a_mole import *
from .app_stop_watch import *
from .app_weather_jp import *
from .app_window_check_linux import *
from .app_communicate_deck import *
from .app_sync_deck_page import *
