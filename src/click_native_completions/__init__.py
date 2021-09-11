import os
import typing as t

import click

from ._common import Completer
from .bash_impl import BashCompleter
from .zsh_impl import ZshCompleter


def _get_completer_cls(
    shell: t.Optional[str] = None,
) -> t.Type[Completer]:
    if shell is None:
        shell = "bash"  # default to bash completion
        if "SHELL" in os.environ:  # see if shell matches, e.g. `/bin/zsh`
            if os.path.basename(os.environ["SHELL"]) == "zsh":
                shell = "zsh"
    return {
        "zsh": ZshCompleter,
        "bash": BashCompleter,
    }.get(shell, BashCompleter)


def generate_completion(command: click.Command, shell: t.Optional[str] = None) -> str:
    completer_cls = _get_completer_cls(shell=shell)
    return completer_cls(command).gen_completion()


def print_completion(command: click.Command, shell: t.Optional[str] = None) -> None:
    click.echo(generate_completion(command, shell=shell))
