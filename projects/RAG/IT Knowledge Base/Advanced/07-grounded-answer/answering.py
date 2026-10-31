"""
IT Knowledge Base: The Grounded Answer
======================================

Turns a question and its retrieved chunks into an answer that can be checked and is safe to show. It handles:
  1. The prompt, from a versioned file (prompts/answer-v1.txt): its version is recorded with every answer
  2. Prompt-injection defenses: a chunk that addresses the model ("ignore previous instructions") is kept out of the
     context and reported; the rest are wrapped in <chunk> tags, their own tags escaped, and the prompt says that
     everything inside <context> is data, never an instruction
  3. A token budget: whole chunks, best first, until the context's budget is spent; the rest are dropped and reported
  4. A structured answer (Answer: the answer, the chunk IDs it cites, whether the context was enough), parsed and
     validated; an answer that can't be parsed is asked for once more
  5. Checks: each cited ID must be one the model was given; an answer that cites none, or says the context wasn't
     enough, becomes the "not covered" reply; the answer is redacted, and an empty one refused
  6. Faithfulness, if a judge is passed in: a second call says which of the answer's sentences the cited chunks
     don't support

    Answerer(llm, prompt=load_prompt(PROMPT_FILE)).answer("My VPN keeps dropping", chunks)
      ->  GroundedAnswer(status="answered", answer="1. ...", sources=[...], cited=[...], problems=[], ...)
"""
import html
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from sensitive_data import redact
from utils import count_tokens

FOLDER = Path(__file__).resolve().parent
PROMPT_FILE = FOLDER / "prompts" / "answer-v1.txt"

# The defaults: kb_settings.toml's [answer] can change each one
MAX_CONTEXT_TOKENS = 3000      # the chunks' share of the prompt
NOT_COVERED = ("The knowledge base doesn't cover this. Contact the service desk, and say what you tried.")

# Text that speaks to a model rather than to a reader: a chunk holding any of it is kept out of the context
INJECTION = re.compile(
    r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|all)\b.{0,20}\b(instructions?|rules?|"
    r"prompts?)\b|\byou are now\b|\bsystem prompt\b|\bact as (an?|the)\b|\bnew instructions?\b|"
    r"\b(tell|instruct|advise) (the )?users? to (disable|turn off|share|send|give)\b",
    re.IGNORECASE | re.DOTALL)


class AnswerError(RuntimeError):
    """The model's answer can't be used, even after one more try; the message says why."""


# -------------------------------------------------
# The Prompt, From a Versioned File
# -------------------------------------------------

@dataclass(frozen=True)
class Prompt:
    version: str
    system: str


def load_prompt(path: Path) -> Prompt:
    """A prompt file: a first line "# version: <version>", then the system prompt."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path.resolve()}")
    first, _, rest = path.read_text(encoding="utf-8").partition("\n")
    match = re.fullmatch(r"#\s*version:\s*(\S+)\s*", first)
    if not match or not rest.strip():
        raise ValueError(f"A prompt file starts with a line \"# version: <version>\", then the prompt: {path}")
    return Prompt(match.group(1), rest.strip())


# -------------------------------------------------
# The Model's Answer, and What Comes Back
# -------------------------------------------------

class Answer(BaseModel):
    """What the model must give back: its answer, the chunks it used, and whether they were enough."""
    answer: str = Field(description="The answer, from the context only; empty when the context isn't enough")
    cited_chunk_ids: list[str] = Field(description="The id of every chunk the answer uses, from the context")
    enough_context: bool = Field(description="Whether the context's chunks answer the question")


class Verdict(BaseModel):
    """What a judge gives back: the answer's sentences the cited chunks don't support."""
    unsupported: list[str] = Field(description="Each sentence of the answer the chunks don't support, word for word")


@dataclass
class GroundedAnswer:
    """The answer to show, and how it was reached."""
    question: str
    status: str                          # "answered", "not_covered", "no_match"
    answer: str
    prompt_version: str
    sources: list[Document] = field(default_factory=list)   # the chunks the answer cites, in the order given
    cited: list[str] = field(default_factory=list)          # their IDs
    problems: list[str] = field(default_factory=list)       # what the checks found
    flagged: list[str] = field(default_factory=list)        # chunks kept out of the context: they address the model
    dropped: list[str] = field(default_factory=list)        # chunks past the token budget
    redacted: list[str] = field(default_factory=list)       # sensitive values taken out of the answer
    context_tokens: int = 0
    prompt_tokens: int = 0              # estimated: the system prompt, the question and the context
    answer_tokens: int = 0
    usage: dict[str, int] = field(default_factory=dict)     # the model's own token counts, when it gives them
    calls: int = 0
    faithfulness: float | None = None   # the share of sentences the judge found supported
    unsupported: list[str] = field(default_factory=list)
    seconds: float = 0.0


def extractive_stand_in(messages: list[BaseMessage]) -> dict[str, Any]:
    """
    A stand-in for the chat model, used when [answer] provider is "fake": it "answers" with the first two sentences
    of the first chunk in the context, and cites it. It reads no meaning, but every check around it runs as it would.
    """
    found = re.search(r'<chunk id="([^"]*)"[^>]*>\n(.*?)\n</chunk>', str(messages[-1].content), re.DOTALL)
    if not found:
        parsed = Answer(answer="", cited_chunk_ids=[], enough_context=False)
    else:
        body = html.unescape(found.group(2)).split("\n", 1)[-1].split(": ", 1)[-1]
        sentences = re.split(r"(?<=[^\d\s][.!?])\s+", body)
        parsed = Answer(answer=" ".join(sentences[:2]), cited_chunk_ids=[html.unescape(found.group(1))],
                        enough_context=True)
    return {"raw": AIMessage(content=parsed.model_dump_json()), "parsed": parsed, "parsing_error": None}


# -------------------------------------------------
# Answerer Class - Question and Chunks to a Checked Answer
# -------------------------------------------------

class Answerer:
    """
    Answers a question from its retrieved chunks, checked.

    Step 1: Configure: the constructor stores the model (as a runnable that gives back a structured Answer), the
            prompt and the limits; nothing is called
    Step 2: answer() gives a GroundedAnswer: "answered", "not_covered" or "no_match"
    """

    def __init__(self, llm, *, prompt: Prompt, max_context_tokens: int = MAX_CONTEXT_TOKENS,
                 not_covered: str = NOT_COVERED, judge=None, length_function: Callable[[str], int] = count_tokens):
        """
        Args:
            llm: a runnable: messages in, {"raw": the model's message, "parsed": an Answer, "parsing_error": ...} out,
                 as a LangChain chat model's with_structured_output(Answer, include_raw=True) gives
            prompt: the system prompt and its version (load_prompt())
            max_context_tokens: the chunks' share of the prompt
            not_covered: the reply when the knowledge base doesn't cover the question
            judge: a runnable: messages in, a Verdict out (a chat model's with_structured_output(Verdict)); None: no
                   faithfulness check
            length_function: counts a text's tokens
        """
        self.llm = llm
        self.prompt = prompt
        self.max_context_tokens = max_context_tokens
        self.not_covered = not_covered
        self.judge = judge
        self.length_function = length_function

    def answer(self, question: str, chunks: list[Document], *, no_match: bool = False) -> GroundedAnswer:
        """The checked answer to a question, from its chunks (best first). no_match: retrieval found nothing that
        fits, so the model isn't asked."""
        started = time.perf_counter()
        result = GroundedAnswer(question, "no_match", self.not_covered, self.prompt.version)
        if no_match or not chunks:
            result.seconds = time.perf_counter() - started
            return result

        # Step 2a: Keep out every chunk that speaks to the model, then fit the rest in the budget, best first
        context: list[Document] = []
        for chunk in chunks:
            chunk_id = chunk.metadata.get("chunk_id", "?")
            if INJECTION.search(chunk.page_content):
                result.flagged.append(chunk_id)
                continue
            tokens = self.length_function(chunk.page_content)
            if result.context_tokens + tokens > self.max_context_tokens:
                result.dropped.append(chunk_id)
                continue
            context.append(chunk)
            result.context_tokens += tokens
        if not context:
            result.status = "not_covered"
            result.problems.append("no chunk could be given to the model")
            result.seconds = time.perf_counter() - started
            return result

        # Step 2b: Ask, with the context delimited; an answer that can't be parsed is asked for once more
        messages = self.messages(question, context)
        result.prompt_tokens = sum(self.length_function(str(message.content)) for message in messages)
        parsed = self._ask(messages, result)

        # Step 2c: Check the citations: only chunks it was given count
        given = {chunk.metadata.get("chunk_id"): chunk for chunk in context}
        unknown = [chunk_id for chunk_id in parsed.cited_chunk_ids if chunk_id not in given]
        if unknown:
            result.problems.append(f"it cited {len(unknown)} chunk{'s' if len(unknown) > 1 else ''} it wasn't "
                                   f"given ({', '.join(unknown)}): left out")
        result.cited = [chunk_id for chunk_id in dict.fromkeys(parsed.cited_chunk_ids) if chunk_id in given]
        result.sources = [given[chunk_id] for chunk_id in given if chunk_id in result.cited]

        # Step 2d: Not enough context, no citation, or no answer: the "not covered" reply, never a guess
        text = parsed.answer.strip()
        if not parsed.enough_context:
            result.status = "not_covered"
        elif not result.cited:
            result.status = "not_covered"
            result.problems.append("it answered without citing a chunk it was given: shown as not covered")
        elif not text:
            result.status = "not_covered"
            result.problems.append("it said the context was enough, but gave no answer: shown as not covered")
        else:
            # Step 2e: Nothing sensitive reaches the user, even if it reached the model
            text, findings = redact(text)
            result.redacted = [f"{found.kind} {found.masked}" for found in findings]
            result.status, result.answer = "answered", text
            result.answer_tokens = self.length_function(text)
            if self.judge is not None:
                self._judge(result)
        if result.status == "not_covered":
            result.sources, result.cited = [], []
        result.seconds = time.perf_counter() - started
        return result

    def messages(self, question: str, context: list[Document]) -> list[BaseMessage]:
        """The system prompt, then the question and the context: each chunk in a <chunk> tag with its id, its text's
        own < and > escaped, so no chunk can close the tag and speak outside it."""
        blocks = "\n".join(
            f'<chunk id="{html.escape(chunk.metadata.get("chunk_id", "?"))}" '
            f'title="{html.escape(chunk.metadata.get("title", ""))}">\n{html.escape(chunk.page_content, quote=False)}'
            f"\n</chunk>" for chunk in context)
        return [SystemMessage(self.prompt.system),
                HumanMessage(f"Question: {question}\n\n<context>\n{blocks}\n</context>")]

    def _ask(self, messages: list[BaseMessage], result: GroundedAnswer) -> Answer:
        problem = "no answer"
        for _ in range(2):
            result.calls += 1
            reply: dict[str, Any] = self.llm.invoke(messages)
            usage = getattr(reply.get("raw"), "usage_metadata", None) or {}
            for name in ("input_tokens", "output_tokens"):
                result.usage[name] = result.usage.get(name, 0) + int(usage.get(name, 0))
            parsed = reply.get("parsed")
            if isinstance(parsed, Answer):
                return parsed
            try:
                return Answer.model_validate(parsed)
            except ValidationError as err:
                problem = str(reply.get("parsing_error") or err).splitlines()[0]
        raise AnswerError(f"The model's answer couldn't be read twice ({problem})")

    def _judge(self, result: GroundedAnswer) -> None:
        """Ask the judge which sentences the cited chunks don't support; the share supported is faithfulness."""
        sources = "\n\n".join(chunk.page_content for chunk in result.sources)
        verdict: Verdict = self.judge.invoke([
            SystemMessage("Say which sentences of the answer the sources don't support. A sentence is supported "
                          "when the sources say it, or plainly imply it."),
            HumanMessage(f"Sources:\n{sources}\n\nAnswer:\n{result.answer}")])
        result.calls += 1
        sentences = [part for part in re.split(r"(?<=[.!?])\s+", result.answer) if part.strip()]
        result.unsupported = [sentence for sentence in verdict.unsupported if sentence.strip()]
        result.faithfulness = round(1 - min(len(result.unsupported), len(sentences)) / len(sentences), 3) \
            if sentences else None
