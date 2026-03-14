from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Estimate token count. Uses tiktoken if available, else len(text) // 4."""
    if not text:
        return 0
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


# ---------------------------------------------------------------------------
# Compressor Protocol
# ---------------------------------------------------------------------------

class Compressor(Protocol):
    def compress(self, text: str) -> str:
        """Return compressed version of text."""
        ...

    def name(self) -> str:
        """Human-readable name for this compressor."""
        ...


# ---------------------------------------------------------------------------
# Built-in Compressors
# ---------------------------------------------------------------------------

class WhitespaceCompressor:
    def name(self) -> str:
        return "whitespace"

    def compress(self, text: str) -> str:
        lines = text.split("\n")
        processed: list[str] = []
        for line in lines:
            # Preserve intentional indentation (2+ spaces or tab at start)
            stripped = line.rstrip()
            if stripped and (stripped[0] == "\t" or (len(stripped) > 0 and line[:2] == "  ")):
                # Preserve leading whitespace, collapse internal runs
                leading = len(line) - len(line.lstrip())
                prefix = line[:leading]
                rest = re.sub(r"[ \t]+", " ", line[leading:]).rstrip()
                processed.append(prefix + rest)
            else:
                collapsed = re.sub(r"[ \t]+", " ", stripped)
                processed.append(collapsed)

        result = "\n".join(processed)
        # Collapse 3+ consecutive newlines to exactly 2
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result


class FillerPhraseCompressor:
    _PHRASES: list[str] = [
        "Certainly! ",
        "Of course! ",
        "Sure! ",
        "Absolutely! ",
        "Great! ",
        "I'd be happy to ",
        "I would be happy to ",
        "As an AI language model, ",
        "As an AI, ",
        "I hope this helps!",
        "I hope that helps!",
        "Let me know if you have any questions.",
        "Feel free to ask if you need more help.",
    ]

    def __init__(self) -> None:
        self._pattern = re.compile(
            "|".join(re.escape(p) for p in self._PHRASES),
            flags=re.IGNORECASE,
        )

    def name(self) -> str:
        return "filler_phrases"

    def compress(self, text: str) -> str:
        return self._pattern.sub("", text)


class JSONMinifier:
    def name(self) -> str:
        return "json_minifier"

    def compress(self, text: str) -> str:
        try:
            return json.dumps(json.loads(text), separators=(",", ":"))
        except (json.JSONDecodeError, ValueError):
            return text


# ---------------------------------------------------------------------------
# CompressionResult
# ---------------------------------------------------------------------------

@dataclass
class CompressionResult:
    original: str
    compressed: str
    original_tokens: int
    compressed_tokens: int

    @property
    def saved_tokens(self) -> int:
        return self.original_tokens - self.compressed_tokens

    @property
    def compression_ratio(self) -> float:
        """compressed_tokens / original_tokens. Lower = better."""
        if self.original_tokens == 0:
            return 1.0
        return self.compressed_tokens / self.original_tokens

    @property
    def saved_pct(self) -> float:
        """Percentage of tokens saved. 0.0–100.0."""
        if self.original_tokens == 0:
            return 0.0
        return (self.saved_tokens / self.original_tokens) * 100.0


# ---------------------------------------------------------------------------
# CompressionPipeline
# ---------------------------------------------------------------------------

class CompressionPipeline:
    def __init__(self, compressors: list[Compressor] | None = None) -> None:
        if compressors is None:
            self._compressors: list[Compressor] = [
                WhitespaceCompressor(),
                FillerPhraseCompressor(),
                JSONMinifier(),
            ]
        else:
            self._compressors = list(compressors)

    def add(self, compressor: Compressor) -> "CompressionPipeline":
        """Append a compressor. Returns self for chaining."""
        self._compressors.append(compressor)
        return self

    def compress(self, text: str) -> CompressionResult:
        original_tokens = estimate_tokens(text)
        result = text
        for compressor in self._compressors:
            result = compressor.compress(result)
        compressed_tokens = estimate_tokens(result)
        return CompressionResult(
            original=text,
            compressed=result,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
        )


# ---------------------------------------------------------------------------
# Optional heavy backend: LLMLingua-2
# ---------------------------------------------------------------------------
# For >3× compression with <2% quality loss, integrate LLMLingua-2:
#
#   pip install llmlingua
#
#   from llmlingua import PromptCompressor
#
#   class LLMLinguaCompressor:
#       def __init__(self, ratio: float = 0.5):
#           self._compressor = PromptCompressor("microsoft/llmlingua-2-xlm-roberta-large-meetingbank")
#           self._ratio = ratio
#       def compress(self, text: str) -> str:
#           return self._compressor.compress_prompt(text, rate=self._ratio)["compressed_prompt"]
#       def name(self) -> str:
#           return f"llmlingua2(ratio={self._ratio})"
#
# Add to a pipeline: pipeline.add(LLMLinguaCompressor(ratio=0.5))
# ---------------------------------------------------------------------------
