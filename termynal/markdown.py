import re
from textwrap import dedent
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Union,
)

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor

if TYPE_CHECKING:  # pragma:no cover
    from markdown import core


class Command(NamedTuple):
    prompt: str
    lines: List[str]


class Comment(NamedTuple):
    lines: List[str]


class Output(NamedTuple):
    lines: List[str]


class Progress:
    def __repr__(self) -> str:  # pragma:no cover
        return "Progress()"


ParsedBlock = Union[Command, Comment, Output, Progress]


def make_regex_prompts(prompt_literal_start: Iterable[str]) -> "re.Pattern[str]":
    prompt_literal_start = [re.escape(p).strip() for p in prompt_literal_start]
    prompt_to_replace = {
        ">": "&gt;",
        "<": "&lt;",
    }
    for p, code in prompt_to_replace.items():
        for i, prompt in enumerate(prompt_literal_start):
            prompt_literal_start[i] = prompt.replace(p, code)
    prompt_literal_start_re = "|".join(f"{p} " for p in prompt_literal_start)
    return re.compile(f"^({prompt_literal_start_re})")


class Termynal:
    def __init__(
        self,
        title: Optional[str] = None,
        prompt_literal_start: Iterable[str] = ("$",),
        progress_literal_start="---&gt; 100%",
        comment_literal_start="# ",
    ):
        self.title = title
        self.regex_prompts = make_regex_prompts(prompt_literal_start)
        self.progress_literal_start = progress_literal_start
        self.comment_literal_start = comment_literal_start

    def parse(self, code_lines: List[str]) -> List[ParsedBlock]:
        parsed: List[ParsedBlock] = []
        multiline = False
        used_prompt = None
        prev: Optional[ParsedBlock] = None
        for line in code_lines:
            if match := self.regex_prompts.match(line):
                used_prompt = match.group()
                prev = Command(used_prompt.strip(), [line.rsplit(used_prompt)[1]])
                parsed.append(prev)
                multiline = bool(line.endswith("\\"))

            elif multiline:
                if prev and isinstance(prev, Command):
                    prev.lines.append(line)
                multiline = bool(line.endswith("\\"))

            elif line.startswith(self.comment_literal_start):
                prev = None
                parsed.append(Comment([line]))

            elif line.startswith(self.progress_literal_start):
                prev = None
                parsed.append(Progress())

            elif prev and isinstance(prev, Output):
                prev.lines.append(line)
            else:
                prev = Output([line])
                parsed.append(prev)

        return parsed

    def convert(self, code: str) -> str:
        code_lines: List[str] = []
        if self.title is not None:
            code_lines.append(
                f'<div class="termy" data-termynal data-ty-title="{self.title}">',
            )
        else:
            code_lines.append('<div class="termy">')

        for block in self.parse(code.split("\n")):
            if isinstance(block, Command):
                lines = "\n".join(block.lines)
                code_lines.append(
                    f'<span data-ty="input" data-ty-prompt="{block.prompt}">'
                    f"{lines}</span>",
                )

            elif isinstance(block, Comment):
                lines = "\n".join(block.lines)
                code_lines.append(
                    f'<span class="termynal-comment" data-ty>{lines}</span>',
                )

            elif isinstance(block, Progress):
                code_lines.append('<span data-ty="progress"></span>')

            elif isinstance(block, Output):
                lines = "<br>".join(block.lines)
                code_lines.append(f"<span data-ty>{lines}</span>")

        code_lines.append("</div>")
        return "".join(code_lines)


class TermynalPreprocessor(Preprocessor):
    ty_comment = "<!-- termynal -->"
    marker = "9HDrdgVBNLga"
    FENCED_BLOCK_RE = re.compile(
        dedent(
            r"""
            (?P<fence>^(?:~{3,}|`{3,}))[ ]*   # opening fence
            ((\{(?P<attrs>[^\}\n]*)\})|       # (optional {attrs} or
            (\.?(?P<lang>[\w#.+-]*)[ ]*)?     # optional (.)lang
            (hl_lines=(?P<quot>"|')           # optional hl_lines)
            (?P<hl_lines>.*?)(?P=quot)[ ]*)?)
            \n                                # newline (end of opening fence)
            (?P<code>.*?)(?<=\n)              # the code block
            (?P=fence)[ ]*$                   # closing fence
        """,
        ),
        re.MULTILINE | re.DOTALL | re.VERBOSE,
    )

    def __init__(self, config: Dict[str, Any], md: "core.Markdown"):
        self.title = config.get("title", None)
        self.prompt_literal_start = config.get("prompt_literal_start", ("$ ",))

        super(TermynalPreprocessor, self).__init__(md=md)

    def run(self, lines: List[str]) -> List[str]:
        placeholder_i = 0
        text = "\n".join(lines)
        store = {}
        while 1:
            m = self.FENCED_BLOCK_RE.search(text)
            if m:
                code = m.group("code")
                placeholder = f"{self.marker}-{placeholder_i}"
                placeholder_i += 1
                store[placeholder] = (code, text[m.start() : m.end()])
                text = f"{text[:m.start()]}\n{placeholder}\n{text[m.end():]}"
            else:
                break

        termynal = Termynal(
            title=self.title,
            prompt_literal_start=self.prompt_literal_start,
        )

        new_lines: List[str] = []
        is_ty_code = False
        for line in text.split("\n"):
            if line.startswith(self.ty_comment):
                is_ty_code = True
                continue

            if is_ty_code and line in store:
                new_lines.append(termynal.convert(self._escape(store[line][0])))
                is_ty_code = False
            elif line in store:
                new_lines.append(store[line][1])
            else:
                new_lines.append(line)

        return new_lines

    def _escape(self, txt: str) -> str:
        txt = txt.replace("&", "&amp;")
        txt = txt.replace("<", "&lt;")
        txt = txt.replace(">", "&gt;")
        txt = txt.replace('"', "&quot;")
        return txt  # noqa:RET504


class TermynalExtension(Extension):
    def __init__(self, *args: Any, **kwargs: Any):
        self.config = {
            "title": [
                "bash",
                "Default: 'bash'",
            ],
            "prompt_literal_start": [
                [
                    "$",
                ],
                "A list of prompt characters start to consider as console - "
                "Default: ['$']",
            ],
        }

        super(TermynalExtension, self).__init__(*args, **kwargs)

    def extendMarkdown(self, md: "core.Markdown") -> None:  # noqa:N802
        """Register the extension."""
        md.registerExtension(self)
        config = self.getConfigs()
        md.preprocessors.register(TermynalPreprocessor(config, md), "termynal", 35)


def makeExtension(  # noqa:N802  # pylint:disable=invalid-name
    *args: Any,
    **kwargs: Any,
) -> TermynalExtension:
    """Return extension."""
    return TermynalExtension(*args, **kwargs)
