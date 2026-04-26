from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from llm_profiles import (
    OpenAICompatibleLLMClient,
    build_llm_client,
    get_profile,
    list_profiles,
    require_api_key,
    validate_profile_runtime,
)
from security import sanitize_secret_text


class APITimeoutError(Exception):
    pass


class TestLLMProfiles(unittest.TestCase):
    def test_minimax_profile_config(self) -> None:
        profile = get_profile("minimax")
        self.assertEqual(profile.profile, "minimax")
        self.assertEqual(profile.provider, "minimax")
        self.assertEqual(profile.model, "MiniMax-M2.7")
        self.assertEqual(profile.api_key_env, "MINIMAX_API_KEY")
        self.assertEqual(profile.temperature, 0)
        self.assertEqual(profile.timeout_ms, 120_000)
        self.assertIsNone(profile.max_tokens)

    def test_deepseek_profile_config(self) -> None:
        profile = get_profile("deepseek")
        self.assertEqual(profile.profile, "deepseek")
        self.assertEqual(profile.provider, "deepseek")
        self.assertEqual(profile.model, "deepseek-v4-flash")
        self.assertEqual(profile.api_key_env, "DEEPSEEK_API_KEY")
        self.assertEqual(profile.temperature, 0)
        self.assertEqual(profile.timeout_ms, 120_000)
        self.assertIsNone(profile.max_tokens)

    def test_codex_proxy_profile_config(self) -> None:
        profile = get_profile("codex-proxy")
        self.assertEqual(profile.profile, "codex-proxy")
        self.assertEqual(profile.provider, "openai-compatible")
        self.assertEqual(profile.model, "GPT-5.3 Codex")
        self.assertEqual(profile.api_key_env, "CODEX_PROXY_API_KEY")
        self.assertEqual(profile.base_url, "https://zhaoshuyue.net.cn/v1")
        self.assertEqual(profile.temperature, 0)
        self.assertEqual(profile.timeout_ms, 120_000)
        self.assertIsNone(profile.max_tokens)

    def test_public_profiles_do_not_include_api_key_values(self) -> None:
        profiles = {p["profile"]: p for p in list_profiles()}
        self.assertEqual(set(profiles), {"minimax", "deepseek", "codex-proxy"})
        self.assertTrue(all("apiKey" not in p for p in profiles.values()))
        self.assertTrue(all("apiKeyEnv" in p for p in profiles.values()))

    def test_invalid_profile_fails_before_api_call(self) -> None:
        with patch("llm_profiles.OpenAI") as openai_cls:
            with self.assertRaisesRegex(ValueError, "invalid llm profile"):
                build_llm_client("unknown")
        openai_cls.assert_not_called()

    def test_missing_api_key_fails_before_api_call(self) -> None:
        cases = [
            ("minimax", "MINIMAX_API_KEY"),
            ("deepseek", "DEEPSEEK_API_KEY"),
            ("codex-proxy", "CODEX_PROXY_API_KEY"),
        ]
        for profile_name, env_name in cases:
            with self.subTest(profile=profile_name), patch.dict(os.environ, {}, clear=True), patch("llm_profiles.OpenAI") as openai_cls:
                profile = get_profile(profile_name)
                with self.assertRaisesRegex(RuntimeError, env_name):
                    require_api_key(profile, allow_mock=False)
                with self.assertRaisesRegex(RuntimeError, env_name):
                    build_llm_client(profile_name)
                openai_cls.assert_not_called()

    def test_mock_client_does_not_require_api_key_or_openai_client(self) -> None:
        with patch.dict(os.environ, {"JAVA2GO_LLM_MOCK": "1"}, clear=True), patch("llm_profiles.OpenAI") as openai_cls:
            client = build_llm_client("codex-proxy")
            resp = client.generate([{"role": "user", "content": "hello"}])

        openai_cls.assert_not_called()
        self.assertEqual(resp.llm_call_status, "success")
        self.assertEqual(resp.profile, "codex-proxy")
        self.assertIsNone(resp.usage.total_tokens)

    def test_uncertain_provider_endpoint_fails_before_api_call(self) -> None:
        cases = [
            ("minimax", "MINIMAX_API_KEY", "MINIMAX_BASE_URL"),
            ("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
        ]
        for profile_name, key_env, base_url_env in cases:
            with self.subTest(profile=profile_name), patch.dict(os.environ, {key_env: "test-key"}, clear=True), patch("llm_profiles.OpenAI") as openai_cls:
                with self.assertRaisesRegex(RuntimeError, base_url_env):
                    validate_profile_runtime(get_profile(profile_name), allow_mock=False)
                with self.assertRaisesRegex(RuntimeError, base_url_env):
                    build_llm_client(profile_name)
                openai_cls.assert_not_called()

    def test_token_usage_present(self) -> None:
        client = self._fake_client(
            response=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )
        )
        resp = client.generate([{"role": "user", "content": "hello"}])
        self.assertEqual(resp.llm_call_status, "success")
        self.assertEqual(resp.usage.prompt_tokens, 10)
        self.assertEqual(resp.usage.completion_tokens, 20)
        self.assertEqual(resp.usage.total_tokens, 30)

    def test_token_usage_missing_is_unknown_not_fabricated(self) -> None:
        client = self._fake_client(
            response=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=None,
            )
        )
        resp = client.generate([{"role": "user", "content": "hello"}])
        self.assertEqual(resp.llm_call_status, "success")
        self.assertIsNone(resp.usage.prompt_tokens)
        self.assertIsNone(resp.usage.completion_tokens)
        self.assertIsNone(resp.usage.total_tokens)

    def test_timeout_error_is_retryable_and_sanitized(self) -> None:
        client = self._fake_client(error=APITimeoutError("MINIMAX_API_KEY=TEST_REDACT_ME"))
        resp = client.generate([{"role": "user", "content": "hello"}])
        self.assertEqual(resp.llm_call_status, "error")
        self.assertIsNotNone(resp.error)
        self.assertTrue(resp.error.retryable)
        self.assertNotIn("TEST_REDACT_ME", resp.error.message)
        self.assertIn("[REDACTED]", resp.error.message)

    def test_provider_error_is_not_retryable(self) -> None:
        client = self._fake_client(error=RuntimeError("provider down"))
        resp = client.generate([{"role": "user", "content": "hello"}])
        self.assertEqual(resp.llm_call_status, "error")
        self.assertIsNotNone(resp.error)
        self.assertFalse(resp.error.retryable)

    def test_malformed_response_is_error(self) -> None:
        client = self._fake_client(response=SimpleNamespace(choices=[], usage=None))
        resp = client.generate([{"role": "user", "content": "hello"}])
        self.assertEqual(resp.llm_call_status, "error")
        self.assertIsNotNone(resp.error)
        self.assertIn("MalformedResponse", resp.error.message)

    def test_sanitize_secret_text(self) -> None:
        text = sanitize_secret_text("MINIMAX_API_KEY=TEST_REDACT_ME api_key=ANOTHER_TEST_SECRET")
        self.assertNotIn("TEST_REDACT_ME", text)
        self.assertNotIn("ANOTHER_TEST_SECRET", text)
        self.assertIn("[REDACTED]", text)

    def _fake_client(self, *, response: object | None = None, error: Exception | None = None) -> OpenAICompatibleLLMClient:
        fake_create = Mock()
        if error is not None:
            fake_create.side_effect = error
        else:
            fake_create.return_value = response
        fake_openai = Mock()
        fake_openai.chat.completions.create = fake_create
        with patch.dict(os.environ, {"CODEX_PROXY_API_KEY": "test-key"}, clear=True), patch("llm_profiles.OpenAI", return_value=fake_openai):
            return OpenAICompatibleLLMClient(get_profile("codex-proxy"))


if __name__ == "__main__":
    unittest.main()
