import typing as t

import click


class ContextTree:
    def __init__(
        self,
        cmd: click.Command,
        info_name: t.Optional[str] = None,
        parent_ctx: t.Optional[click.Context] = None,
    ):
        self.cmd = cmd
        self.name = info_name or cmd.name
        self.parent_ctx = parent_ctx

    def _walk(
        self,
    ) -> t.Tuple[click.Context, t.List[click.Context], t.List["ContextTree"]]:
        current_ctx = click.Context(
            self.cmd, info_name=self.name, parent=self.parent_ctx
        )
        cmds, subtrees = [], []

        for subcmdname, subcmd in getattr(self.cmd, "commands", {}).items():
            # explicitly skip hidden commands
            if subcmd.hidden:
                continue

            if isinstance(subcmd, click.Group):
                subtrees.append(ContextTree(subcmd, parent_ctx=current_ctx))
            else:
                cmds.append(
                    click.Context(subcmd, info_name=subcmdname, parent=current_ctx)
                )

        return (current_ctx, cmds, subtrees)

    def __iter__(self) -> t.Generator[click.Context, None, None]:
        ctx, subcmds, subtrees = self._walk()
        yield ctx
        yield from subcmds
        for st in subtrees:
            yield from st


class Completer:
    @property
    def epilogue(self) -> str:
        return ""

    @property
    def prologue(self) -> str:
        return ""

    def _slugify(self, s: str) -> str:
        return s.replace(" ", "_").replace("-", "_")

    def __init__(
        self,
        command: click.Command,
        command_name: t.Optional[str] = None,
    ) -> None:
        self.name = command_name or command.name
        if not self.name:
            raise ValueError(
                "cannot generate completions unless the command name is set"
            )
        self.root_cmd = command
        self.root_slug = self._slugify(self.name)
        self.slug = f"__{self.root_slug}__comp"

    def group_completer(self, ctx: click.Context) -> t.Generator[str, None, None]:
        raise NotImplementedError

    def cmd_completer(self, ctx: click.Context) -> t.Generator[str, None, None]:
        raise NotImplementedError

    def _gen_completion(self) -> t.Generator[str, None, None]:
        yield self.prologue
        for ctx in ContextTree(self.root_cmd, self.name):
            if isinstance(ctx.command, click.Group):
                yield from self.group_completer(ctx)
            else:
                yield from self.cmd_completer(ctx)
        yield self.epilogue

    def gen_completion(self) -> str:
        return "\n".join(self._gen_completion())


def is_repeatable(o: click.Option) -> bool:
    return o.count or o.multiple


def compute_nargs(o: click.Option) -> int:
    if o.is_flag or o.count:
        return 0
    else:
        return o.nargs


def opt_strs(o: click.Option) -> t.List[str]:
    return list(o.opts) + list(o.secondary_opts)


def slamopts(o: click.Option) -> t.List[str]:
    # two letter options, like `-F` can be slammed if they consume exactly one argument
    if compute_nargs(o) != 1:
        return []
    return [x for x in opt_strs(o) if len(x) < 3]
