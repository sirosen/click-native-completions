import re
import typing as t

import click

from ._common import Completer, compute_nargs, is_repeatable, opt_strs

_ZSH_HELP_ESC_RE = re.compile(r'([`":\[\]])')


class ZshCompleter(Completer):
    DEFAULT_EAGER_EXIT_OPTS = ("-h", "--help")

    @property
    def epilogue(self) -> str:
        return f"compdef {self.slug}_cmd_{self.root_slug} {self.name}"

    def __init__(
        self,
        command: click.Command,
        command_name: t.Optional[str] = None,
        options_causing_eager_exit: t.Optional[t.Tuple[str, ...]] = None,
    ) -> None:
        super().__init__(command, command_name=command_name)
        self.options_causing_eager_exit = (
            options_causing_eager_exit
            if options_causing_eager_exit is not None
            else self.DEFAULT_EAGER_EXIT_OPTS
        )

    def _is_root_ctx(self, ctx: click.Context) -> bool:
        return " " not in ctx.command_path

    def _cmdslug(self, ctx: click.Context) -> str:
        return self._slugify(ctx.command_path)

    def _cmd_completer_name(self, ctx: click.Context) -> str:
        return f"{self.slug}_cmd_{self._cmdslug(ctx)}"

    def _subcmd_describer_name(self, ctx: click.Context) -> str:
        return f"{self.slug}_describe_subcmds_{self._cmdslug(ctx)}"

    def _option_descs(self, o: click.Option) -> t.Generator[str, None, None]:
        nargs = compute_nargs(o)
        argspec = ""
        if isinstance(o.type, click.Choice):
            argspec = ": :(" + " ".join(o.type.choices) + ")"
        elif nargs > 0:
            argspec = ": :( )"

        # escape quotes and colons
        helptext = ("[" + _ZSH_HELP_ESC_RE.sub(r"\\\1", o.help) + "]") if o.help else ""

        # TODO: add mutual exclusivity info from mutexinfo
        # when options are listed in the parenthetical section at the start of an option
        # spec, they are noted as mutually exclusive
        # here we list aliases, so that `--help` and `-h` are considered mutex (for
        # better completion)
        raw_flags = flags = opt_strs(o)

        # append a + if a flag takes one argument and is a short option
        # this indicates that we support option-slamming, as in `-Fjson`
        flags = [
            (f"{flag}+" if len(flag) == 2 and nargs == 1 else flag) for flag in flags
        ]
        # append an = if a flag takes one argument and is a long option
        # this indicates that we support `--format=text`
        flags = [
            (f"{flag}=" if flag.startswith("--") and nargs == 1 else flag)
            for flag in flags
        ]
        if is_repeatable(o):
            flags = [f"*{flag}" for flag in flags]

        # compute the exclusion rule (if applicable)
        excludes = " ".join(raw_flags)
        if is_repeatable(o):
            excludes = ""
        if flags[0] in self.options_causing_eager_exit:
            excludes = excludes + (" " if excludes else "") + "- :"
        if excludes:
            excludes = "(" + excludes + ")"

        if len(flags) == 1:
            yield f'"{excludes}{flags[0]}{helptext}{argspec}"'
        else:
            for flag in flags:
                yield f'"{excludes}{flag}{helptext}{argspec}"'

    def _all_option_descs(self, ctx: click.Context) -> t.List[str]:
        options = [
            x
            for x in ctx.command.params
            if isinstance(x, click.Option) and not x.hidden
        ]
        return [x for o in options for x in self._option_descs(o)]

    def _positional_arg_desc(self, arg_position: int, arg: click.Argument) -> str:
        n = str(arg_position + 1)
        if compute_nargs(arg) == -1:
            n = "*"
        # a zsh positional arg spec uses a double-colon before the message field to
        # indicate optional positional arguments
        opt_colon = "" if arg.required else ":"
        return f'"{n}{opt_colon}:{arg.human_readable_name}: "'

    def _all_positional_arg_descs(self, ctx: click.Context) -> t.List[str]:
        args = [x for x in ctx.command.params if isinstance(x, click.Argument)]
        return [self._positional_arg_desc(i, a) for i, a in enumerate(args)]

    def cmd_completer(self, ctx: click.Context) -> t.Generator[str, None, None]:
        yield f"{self._cmd_completer_name(ctx)}() {{"
        yield "  _arguments \\"
        all_descs = self._all_option_descs(ctx) + self._all_positional_arg_descs(ctx)
        for d in all_descs[:-1]:
            yield f"    {d}  \\"
        yield "    " + all_descs[-1]
        yield "}"

    def group_completer(self, ctx: click.Context) -> t.Generator[str, None, None]:
        this_group = t.cast(click.Group, ctx.command)
        subcommand_names = this_group.commands.keys()
        yield f"{self._subcmd_describer_name(ctx)}() {{"
        yield "  local -a subcmds; subcmds=("
        for n in subcommand_names:
            cmdhelp = this_group.commands[n].get_short_help_str()
            yield f'    "{n}:{cmdhelp}"'
        yield "  )"
        yield f"  _describe -t subcmds '{ctx.command_path} command' subcmds \"$@\""
        yield "}"

        yield f"{self._cmd_completer_name(ctx)}() {{"
        if self._is_root_ctx(ctx):
            yield '  local curcontext="$curcontext" context state state_descr line'
            yield "  typeset -A opt_args"
        yield "  _arguments -C \\"
        for desc in self._all_option_descs(ctx):
            yield f"    {desc} \\"
        # IMPORTANT!
        # This is subtle, but each of these specs MUST have '(-)', indicating
        # mutual exclusivity with additional CLI options
        # This prevents the higher-level command in a tree from eagerly
        # consuming options which follow subcommands
        #
        # For example, if the input command is `foo bar -h`, we *don't*
        # want the `_arguments` call to consume `-h` as an option to the
        # `foo` command
        # It should instead be left un-parsed, and the subsequent `_arguments`
        # call for the `bar` subcommand will pick it up correctly
        #
        # This behavior has been tested and does not mark these matches as
        # mutually exclusive with prior options. Meaning that
        # `foo --format json <TAB>` will run the subcommand description action as
        # desired
        yield f'    "(-): :{self._subcmd_describer_name(ctx)}" \\'
        yield '    "(-)*::arg:->args"'

        yield "  case $state in (args) case $line[1] in"
        for n in subcommand_names:
            funcname = f"{self._cmd_completer_name(ctx)}_{self._slugify(n)}"
            yield f'    "{n}") {funcname} ;;'
        yield "  esac ;; esac"
        yield "}"
