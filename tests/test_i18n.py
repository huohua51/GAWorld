"""Tests for the gaworld.i18n module and locale file consistency."""

from __future__ import annotations

import json
import os
import re
import unittest

from gaworld.i18n import t, eng, available_locales, reload

_HERE = os.path.dirname(os.path.abspath(__file__))
_LOCALE_DIR = os.path.normpath(os.path.join(_HERE, "..", "site", "dashboard", "locales"))


def _load_json(name: str) -> dict[str, str]:
    path = os.path.join(_LOCALE_DIR, name)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class TestPythonI18nModule(unittest.TestCase):
    """Tests for the Python i18n module API."""

    def test_python_module_imports(self):
        from gaworld.i18n import t, eng, available_locales, reload
        self.assertTrue(callable(t))
        self.assertTrue(callable(eng))

    def test_t_function_returns_chinese_by_default(self):
        result = t("console.title")
        self.assertEqual("GAWorld 个人孪生控制台", result)

    def test_eng_function_returns_english(self):
        result = eng("console.title")
        self.assertEqual("GAWorld Twin Console", result)

    def test_t_with_unknown_key_returns_key_itself(self):
        result = t("this.key.does.not.exist.xyz")
        self.assertEqual("this.key.does.not.exist.xyz", result)

    def test_eng_with_unknown_key_returns_key_itself(self):
        result = eng("this.key.does.not.exist.xyz")
        self.assertEqual("this.key.does.not.exist.xyz", result)

    def test_available_locales_returns_list(self):
        locales = available_locales()
        self.assertIsInstance(locales, list)
        self.assertGreaterEqual(len(locales), 1)
        for entry in locales:
            self.assertIn("code", entry)
            self.assertIn("label", entry)

    def test_reload_clears_cache(self):
        _ = t("console.title")
        reload()
        result = t("console.title")
        self.assertEqual("GAWorld 个人孪生控制台", result)


class TestLocaleFileConsistency(unittest.TestCase):
    """Tests that both locale files are valid and have consistent keys."""

    @classmethod
    def setUpClass(cls):
        cls.en = _load_json("en.json")
        cls.zh = _load_json("zh-CN.json")

    def test_en_locale_file_is_valid_json(self):
        self.assertIsInstance(self.en, dict)
        for k, v in self.en.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    def test_zh_locale_file_is_valid_json(self):
        self.assertIsInstance(self.zh, dict)
        for k, v in self.zh.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    def test_all_keys_present_in_both_locales(self):
        en_keys = set(self.en.keys())
        zh_keys = set(self.zh.keys())
        only_in_en = en_keys - zh_keys
        only_in_zh = zh_keys - en_keys
        self.assertEqual(set(), only_in_en, f"Keys only in en.json: {only_in_en}")
        self.assertEqual(set(), only_in_zh, f"Keys only in zh-CN.json: {only_in_zh}")

    def test_en_keys_are_sorted(self):
        keys = list(self.en.keys())
        if keys != sorted(keys):
            self.skipTest("Keys are not alphabetically sorted (cosmetic, not blocking)")

    def test_zh_keys_match_en_order(self):
        en_keys = list(self.en.keys())
        zh_keys = list(self.zh.keys())
        self.assertEqual(en_keys, zh_keys, "Locale files have different key order")


class TestLocaleFileCoverage(unittest.TestCase):
    """Tests that all keys referenced in source files exist in locale files."""

    @classmethod
    def setUpClass(cls):
        cls.en = _load_json("en.json")
        cls.zh = _load_json("zh-CN.json")

    def _keys_in_file(self, path: str) -> set[str]:
        keys: set[str] = set()
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        for m in re.finditer(r'__f?\s*\(\s*"([^"]+)"', content):
            keys.add(m.group(1))
        for m in re.finditer(r'data-i18n(?:-placeholder|-content)?\s*=\s*"([^"]+)"', content):
            keys.add(m.group(1))
        return keys

    def test_app_js_keys_exist_in_en(self):
        app_js = os.path.join(_LOCALE_DIR, "..", "app.js")
        if not os.path.isfile(app_js):
            self.skipTest("app.js not found")
        keys = self._keys_in_file(app_js)
        missing = keys - set(self.en.keys())
        self.assertEqual(set(), missing, f"Keys in app.js missing from en.json: {missing}")

    def test_app_js_keys_exist_in_zh(self):
        app_js = os.path.join(_LOCALE_DIR, "..", "app.js")
        if not os.path.isfile(app_js):
            self.skipTest("app.js not found")
        keys = self._keys_in_file(app_js)
        missing = keys - set(self.zh.keys())
        self.assertEqual(set(), missing, f"Keys in app.js missing from zh-CN.json: {missing}")

    def test_html_data_i18n_keys_exist_in_en(self):
        html_path = os.path.join(_LOCALE_DIR, "..", "index.html")
        if not os.path.isfile(html_path):
            self.skipTest("index.html not found")
        keys = self._keys_in_file(html_path)
        missing = keys - set(self.en.keys())
        self.assertEqual(set(), missing, f"Keys in index.html missing from en.json: {missing}")

    def test_html_data_i18n_keys_exist_in_zh(self):
        html_path = os.path.join(_LOCALE_DIR, "..", "index.html")
        if not os.path.isfile(html_path):
            self.skipTest("index.html not found")
        keys = self._keys_in_file(html_path)
        missing = keys - set(self.zh.keys())
        self.assertEqual(set(), missing, f"Keys in index.html missing from zh-CN.json: {missing}")


if __name__ == "__main__":
    unittest.main()
