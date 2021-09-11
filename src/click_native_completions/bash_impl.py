import typing as t

import click

from ._common import Completer, compute_nargs, opt_strs, slamopts


class BashCompleter(Completer):
    PROLOGUE_FMT = """\
declare -A {x.slug}_subcmds
declare -A {x.slug}_opts
declare -A {x.slug}_opt_nargs
declare -A {x.slug}_slamopts
declare -A {x.slug}_opt_choices
"""

    EPILOGUE_FMT = """
{x.slug}_parse_line() {{
  local compword
  compword="${{COMP_WORDS[$COMP_CWORD]}}"

  local boundary
  boundary=$((${{#COMP_WORDS[@]}} - 2))

  local i=0 toskip=0
  local curopt="" nomoreopts=0
  local curcmd=${{COMP_WORDS[0]}} curword=${{COMP_WORDS[0]}}
  while [ $i -lt $boundary ]; do
    _=$((i++))
    curword=${{COMP_WORDS[$i]}}

    if [ "$curword" = "--" ]; then
      curopt=""
      nomoreopts=1
      continue
    fi

    if [ $toskip -gt 0 ]; then
      _=$((toskip--))
      continue
    fi

    if [[ $nomoreopts -eq 0 ]] && [[ $curword == -* ]]; then
      # if a "slammed" option like `-Ftext` is given, proceed to the next word
      # in the command
      slamopts=${{{x.slug}_slamopts[$curcmd]}}
      for opt in $slamopts; do
        if [[ "$curword" != "$opt" ]] && [[ "$curword" == "$opt"* ]]; then
          continue 2
        fi
      done

      curopt=$curword
      toskip=${{{x.slug}_opt_nargs["$curcmd $curword"]}}
      [ -n "$toskip" ] || toskip=0
      continue
    fi

    for subcmd in ${{{x.slug}_subcmds["$curcmd"]}}; do
      if [ "$curword" = "$subcmd" ]; then
        curcmd="$curcmd $curword"
        continue 2
      fi
    done

    # if this point is reached, the command structure is unrecognized
    # end with the current discovered command
    break
  done
  if [ $toskip -eq 0 ]; then
    curopt=""
  fi

  # if no partial option processing is happening, check to see if the current
  # word, when added, matches a command
  if [ "$toskip" -eq 0 ]; then
    for subcmd in ${{{x.slug}_subcmds["$curcmd"]}}; do
      if [ "$compword" = "$subcmd" ]; then
        curcmd="$curcmd $compword"
        curopt=""
        break
      fi
    done
  fi
  echo "$curcmd"
  echo "$curopt"
  echo "$toskip"
}}

{x.slug}_add_match_to_compreply() {{
  for choice in $1; do
    if [[ "$choice" == "${{COMP_WORDS[$COMP_CWORD]}}"* ]]; then
      COMPREPLY+=("$choice")
    fi
  done
}}

{x.slug}_add_match_for_cmdopt() {{
  local choices="${{{x.slug}_opt_choices["$1"]}}"
  if [ -n "$choices" ]; then
    {x.slug}_add_match_to_compreply "$choices"
  fi
}}

{x.slug}_bash() {{
  COMPREPLY=()
  local curword
  curword="${{COMP_WORDS[$COMP_CWORD]}}"

  local parsed
  readarray -t parsed < <({x.slug}_parse_line)

  local curcmd curopt num_optargs curcmd_w_curopt
  curcmd=${{parsed[0]}}
  curopt=${{parsed[1]}}
  num_optargs=${{parsed[2]}}
  curcmd_w_curopt="$curcmd $curopt"

  case $curword in
    -*)  # option case
      {x.slug}_add_match_to_compreply "${{{x.slug}_opts["$curcmd"]}}"
      ;;
    "")  # next subcommand, option, or option value if no partial word
      if [ "$num_optargs" -gt 0 ]; then
        {x.slug}_add_match_for_cmdopt "$curcmd_w_curopt"
      else
        for subcmd in ${{{x.slug}_subcmds["$curcmd"]}}; do
          COMPREPLY+=("$subcmd")
        done
      fi
      ;;
    *)  # partial word case, subcommand or option argument
      if [ -z "$curopt" ]; then
        {x.slug}_add_match_to_compreply "${{{x.slug}_subcmds["$curcmd"]}}"
      else
        {x.slug}_add_match_for_cmdopt "$curcmd_w_curopt"
      fi
      ;;
  esac
}}

complete -F {x.slug}_bash {x.root_cmd.name}"""  # noqa: E501

    @property
    def prologue(self) -> str:
        return self.PROLOGUE_FMT.format(x=self)

    @property
    def epilogue(self) -> str:
        return self.EPILOGUE_FMT.format(x=self)

    def _common_info(self, ctx: click.Context) -> t.Generator[str, None, None]:
        options = [
            x
            for x in ctx.command.params
            if isinstance(x, click.Option) and not x.hidden
        ]
        joined_opts = " ".join(x for o in options for x in opt_strs(o))
        joined_slamopts = " ".join(x for o in options for x in slamopts(o))
        yield f'{self.slug}_opts["{ctx.command_path}"]="{joined_opts}"'
        yield f'{self.slug}_slamopts["{ctx.command_path}"]="{joined_slamopts}"'
        for o in options:
            nargs = compute_nargs(o)
            for s in opt_strs(o):
                yield f'{self.slug}_opt_nargs["{ctx.command_path} {s}"]="{nargs}"'
        for o in options:
            if isinstance(o.type, click.Choice):
                choices = " ".join(o.type.choices)
                for s in opt_strs(o):
                    yield (
                        f'{self.slug}_opt_choices["{ctx.command_path} {s}"]="{choices}"'
                    )

    def cmd_completer(self, ctx: click.Context) -> t.Generator[str, None, None]:
        # commands do not have any subcommands
        yield f'{self.slug}_subcmds["{ctx.command_path}"]=""'
        yield from self._common_info(ctx)

    def group_completer(self, ctx: click.Context) -> t.Generator[str, None, None]:
        command_names = t.cast(click.Group, ctx.command).commands.keys()
        cmds = " ".join(command_names)
        yield f'{self.slug}_subcmds["{ctx.command_path}"]="{cmds}"'
        yield from self._common_info(ctx)
