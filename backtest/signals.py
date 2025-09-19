from importlib import import_module
from typing import Callable



def load_user_signal(
    module_path: str,
    function_name: str
) -> Callable:
	module = import_module(module_path)
	func = getattr(module, function_name)
	if not callable(func):
		raise TypeError(f"{module_path}.{function_name} is not callable")
	return func
