import json
import pathlib
import tempfile
import unittest

import httpx2
from typesafe_sdk import RetryPolicy, TypeSafeClient

from scraper.jev import FakeJev, Jev, JevError, cache_key

QUESTIONS = {
    "a": {"type": "noul", "instructions": "Q?", "criteria": {"true": "t", "false": "f"}},
    "b": {"type": "choice", "instructions": "C?", "criteria": {"x": None, "y": "why"}},
}
ANSWERS = {"a": {"type": "noul", "noul": 0.9},
           "b": {"type": "choice", "choice": "x", "probabilities": {"x": 0.8, "y": 0.2}, "confidence": 0.7}}


def client_with(handler):
    # a dummy key and a mock transport: no network, no real key
    return TypeSafeClient(api_key="test-key", transport=httpx2.MockTransport(handler), compression=False,
                          retry=RetryPolicy(max_retries=2, backoff_initial=0.01, backoff_max=0.02, timeout=5.0))


class JevWrapper(unittest.TestCase):
    def setUp(self):
        self.cache = pathlib.Path(tempfile.mkdtemp())
        self.bodies = []

    def ok(self, request):
        self.bodies.append(json.loads(request.read()))
        return httpx2.Response(200, json={"model": "jev-1.13.0", "answers": ANSWERS,
                                          "usage": {"input_tokens": 11, "output_tokens": 3}})

    def test_request_shape_answers_and_usage(self):
        jev = Jev(cache_dir=self.cache, client=client_with(self.ok))
        self.assertEqual(jev.ask({"s": 1}, QUESTIONS), ANSWERS)
        body = self.bodies[0]
        self.assertEqual((body["state"], body["model"]), ({"s": 1}, "jev-latest"))
        self.assertEqual(body["questions"], QUESTIONS)
        self.assertEqual(jev.usage, {"requests": 1, "cache_hits": 0, "input_tokens": 11, "output_tokens": 3, "errors": 0})

    def test_cache_hit_makes_no_second_request(self):
        jev = Jev(cache_dir=self.cache, client=client_with(self.ok))
        jev.ask({"s": 1}, QUESTIONS)
        again = Jev(cache_dir=self.cache, client=client_with(self.ok))   # a new run, same cache folder
        self.assertEqual(again.ask({"s": 1}, QUESTIONS), ANSWERS)
        self.assertEqual(len(self.bodies), 1)
        self.assertEqual((again.usage["cache_hits"], again.usage["requests"], again.usage["input_tokens"]), (1, 0, 0))

    def test_other_state_or_model_is_a_cache_miss(self):
        self.assertNotEqual(cache_key({"s": 1}, QUESTIONS, "jev-latest"), cache_key({"s": 2}, QUESTIONS, "jev-latest"))
        self.assertNotEqual(cache_key({"s": 1}, QUESTIONS, "jev-latest"), cache_key({"s": 1}, QUESTIONS, "jev-x"))

    def test_retries_a_429_then_succeeds(self):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx2.Response(429, json={"error": {"message": "slow down"}})
            return self.ok(request)
        jev = Jev(cache_dir=self.cache, client=client_with(handler))
        self.assertEqual(jev.ask({"s": 1}, QUESTIONS), ANSWERS)
        self.assertEqual(len(calls), 2)

    def test_failure_after_retries_raises_jev_error(self):
        jev = Jev(cache_dir=self.cache, client=client_with(lambda r: httpx2.Response(401, json={"error": {}})))
        with self.assertRaises(JevError):
            jev.ask({"s": 1}, QUESTIONS)
        self.assertEqual(jev.usage["errors"], 1)

    def test_fake_jev_is_deterministic_and_counts_tokens(self):
        q = {"p0": {"type": "noul", "instructions": "x", "criteria": {}}}
        state = {"products": [{"title": "Dungeon Delvers Core Rulebook", "shop": "s", "tags": []}]}
        fake = FakeJev()
        self.assertEqual(fake.ask(state, q), fake.ask(state, q))
        self.assertGreater(fake.usage["input_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
