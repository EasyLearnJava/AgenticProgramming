"""
nimbus/answer.py: where the chat's answer comes from. In step 2 it's a fixed answer, the same for every question,
sent a word at a time, the way a model streams its words; step 3 makes it Gemini's.
"""

import asyncio
import re
from collections.abc import AsyncIterator

FIXED_ANSWER = (
    "Hi, I'm Nimbus. Weather answers come later: Gemini joins in step 3, and the weather tools in step 4. Until then, "
    "every question gets this same reply, a word at a time, the way a model streams its words, so you can watch it "
    "arrive or press Stop."
)
# The pause before each word: long enough to watch the answer arrive, and to press Stop before it ends.
WORD_DELAY_SECONDS = 0.06
# A word, with the space before it.
PIECE = re.compile(r"\s*\S+")


async def stream_fixed_answer() -> AsyncIterator[str]:
    """The fixed answer, a piece at a time: each word with the space before it, after a short pause."""
    for piece in PIECE.findall(FIXED_ANSWER):
        await asyncio.sleep(WORD_DELAY_SECONDS)
        yield piece
