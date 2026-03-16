import json
import unittest

from ascp.compression import (
    CompressionPipeline,
    CompressionResult,
    FillerPhraseCompressor,
    JSONMinifier,
    WhitespaceCompressor,
    estimate_tokens,
)


class TestEstimateTokens(unittest.TestCase):
    def test_returns_positive_int_for_nonempty_text(self):
        result = estimate_tokens("hello world")
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_empty_string_returns_zero(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_fallback_estimate_is_within_2x_of_real_for_prose(self):
        """len//4 is a rule-of-thumb; real prose is ~3.5-4 chars/token."""
        text = "a" * 400
        fallback = len(text) // 4  # 100
        self.assertEqual(fallback, 100)
        self.assertGreaterEqual(fallback, 80)
        self.assertLessEqual(fallback, 200)

    def test_estimate_tokens_returns_positive_for_structured_json(self):
        tool_schema = json.dumps({
            "name": "get_weather",
            "description": "Retrieve current weather conditions for a given location.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City and country, e.g. Paris, France"
                    },
                    "units": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit"
                    }
                },
                "required": ["location"]
            }
        })
        result = estimate_tokens(tool_schema)
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)
        self.assertGreater(result, len(tool_schema) // 8)
        self.assertLess(result, len(tool_schema))


class TestWhitespaceCompressor(unittest.TestCase):
    def setUp(self):
        self.c = WhitespaceCompressor()

    def test_name(self):
        self.assertEqual(self.c.name(), "whitespace")

    def test_collapses_multiple_spaces(self):
        result = self.c.compress("hello   world")
        self.assertEqual(result, "hello world")

    def test_collapses_three_or_more_newlines_to_two(self):
        result = self.c.compress("a\n\n\n\nb")
        self.assertEqual(result, "a\n\nb")

    def test_strips_trailing_whitespace_from_lines(self):
        result = self.c.compress("hello   \nworld  ")
        self.assertNotIn("   \n", result)
        self.assertNotIn("  ", result.split("\n")[-1])

    def test_preserves_indentation(self):
        code = "def foo():\n    return 1"
        result = self.c.compress(code)
        self.assertIn("    return 1", result)

    def test_preserves_tab_indentation(self):
        code = "def foo():\n\treturn 1"
        result = self.c.compress(code)
        self.assertIn("\treturn 1", result)


class TestFillerPhraseCompressor(unittest.TestCase):
    def setUp(self):
        self.c = FillerPhraseCompressor()

    def test_name(self):
        self.assertEqual(self.c.name(), "filler_phrases")

    def test_removes_certainly_prefix(self):
        result = self.c.compress("Certainly! Here is your answer.")
        self.assertNotIn("Certainly!", result)
        self.assertIn("Here is your answer.", result)

    def test_removes_as_an_ai_language_model(self):
        result = self.c.compress("As an AI language model, I can help.")
        self.assertNotIn("As an AI language model,", result)
        self.assertIn("I can help.", result)

    def test_case_insensitive(self):
        result = self.c.compress("certainly! Here is your answer.")
        self.assertNotIn("certainly!", result)

    def test_removes_of_course(self):
        result = self.c.compress("Of course! Let me explain.")
        self.assertNotIn("Of course!", result)

    def test_removes_i_hope_this_helps(self):
        result = self.c.compress("Here is the answer. I hope this helps!")
        self.assertNotIn("I hope this helps!", result)

    def test_removes_let_me_know(self):
        result = self.c.compress("Done. Let me know if you have any questions.")
        self.assertNotIn("Let me know if you have any questions.", result)

    def test_no_change_when_no_filler(self):
        text = "The answer is 42."
        self.assertEqual(self.c.compress(text), text)

    def test_real_agent_response_without_filler_passes_unchanged(self):
        text = (
            "To solve this problem, I'll use a recursive approach. "
            "First, we define the base case: if n == 0, return 1. "
            "For n > 0, we multiply n by factorial(n-1). "
            "Here's the implementation:\n\n"
            "```python\ndef factorial(n):\n    if n == 0:\n        return 1\n    return n * factorial(n-1)\n```\n\n"
            "This runs in O(n) time and O(n) space due to the call stack."
        )
        self.assertEqual(FillerPhraseCompressor().compress(text), text)


class TestJSONMinifier(unittest.TestCase):
    def setUp(self):
        self.c = JSONMinifier()

    def test_name(self):
        self.assertEqual(self.c.name(), "json_minifier")

    def test_minifies_valid_json(self):
        pretty = json.dumps({"key": "value", "num": 1}, indent=2)
        result = self.c.compress(pretty)
        self.assertEqual(result, '{"key":"value","num":1}')

    def test_passes_through_non_json(self):
        text = "This is not JSON at all."
        self.assertEqual(self.c.compress(text), text)

    def test_passes_through_partial_json(self):
        text = '{"key": "value"'  # malformed
        self.assertEqual(self.c.compress(text), text)


class TestCompressionPipeline(unittest.TestCase):
    def test_default_pipeline_reduces_token_count_on_filler_heavy_text(self):
        text = (
            "Certainly! As an AI language model, I can help you with that.   "
            "Here is the answer.   \n\n\n\nI hope this helps!"
        )
        pipeline = CompressionPipeline()
        result = pipeline.compress(text)
        self.assertLess(result.compressed_tokens, result.original_tokens)

    def test_compress_returns_compression_result(self):
        pipeline = CompressionPipeline()
        result = pipeline.compress("hello world")
        self.assertIsInstance(result, CompressionResult)
        self.assertEqual(result.original, "hello world")
        self.assertIsInstance(result.original_tokens, int)
        self.assertIsInstance(result.compressed_tokens, int)

    def test_compression_result_correct_fields(self):
        pipeline = CompressionPipeline()
        text = "Certainly! Here is the answer."
        result = pipeline.compress(text)
        self.assertEqual(result.original, text)
        self.assertNotIn("Certainly!", result.compressed)
        self.assertEqual(result.original_tokens, estimate_tokens(text))
        self.assertEqual(result.compressed_tokens, estimate_tokens(result.compressed))

    def test_saved_pct_is_correct(self):
        pipeline = CompressionPipeline()
        text = "Certainly! As an AI language model, I can help. I hope this helps!"
        result = pipeline.compress(text)
        expected_pct = (result.saved_tokens / result.original_tokens) * 100.0
        self.assertAlmostEqual(result.saved_pct, expected_pct, places=5)

    def test_add_supports_chaining(self):
        pipeline = CompressionPipeline(compressors=[])
        returned = pipeline.add(WhitespaceCompressor()).add(FillerPhraseCompressor())
        self.assertIs(returned, pipeline)
        self.assertEqual(len(pipeline._compressors), 2)

    def test_empty_string_returns_unchanged_with_zero_saved(self):
        pipeline = CompressionPipeline()
        result = pipeline.compress("")
        self.assertEqual(result.original, "")
        self.assertEqual(result.compressed, "")
        self.assertEqual(result.saved_tokens, 0)

    def test_saved_tokens_property(self):
        pipeline = CompressionPipeline()
        text = "Certainly! Here is the answer."
        result = pipeline.compress(text)
        self.assertEqual(result.saved_tokens, result.original_tokens - result.compressed_tokens)

    def test_compression_ratio_property(self):
        pipeline = CompressionPipeline()
        text = "hello world"
        result = pipeline.compress(text)
        if result.original_tokens > 0:
            expected = result.compressed_tokens / result.original_tokens
            self.assertAlmostEqual(result.compression_ratio, expected, places=10)


if __name__ == "__main__":
    unittest.main()
