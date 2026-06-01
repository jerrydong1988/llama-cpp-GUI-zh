"""i18n - lightweight internationalization for llama-cpp-GUI-zh.

Usage:
    from i18n import _
    label = _("model path")
    label = _("arch: {arch}").format(arch=name)
"""

import json
import os
import sys


class I18n:
    """Singleton translation manager."""

    def __init__(self):
        self._data = {}
        self._lang = "zh_CN"

    def load(self, lang):
        """Load translations for the given language code."""
        base = self._locales_dir()
        path = os.path.join(base, f"{lang}.json")
        if not os.path.isfile(path):
            path = os.path.join(base, "zh_CN.json")
        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._lang = lang

    @staticmethod
    def _locales_dir():
        if getattr(sys, "frozen", False):
            return os.path.join(sys._MEIPASS, "locales")
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

    @property
    def current_lang(self):
        return self._lang

    @property
    def available_langs(self):
        base = self._locales_dir()
        if not os.path.isdir(base):
            return []
        return sorted(f[:-5] for f in os.listdir(base) if f.endswith(".json"))

    def __call__(self, key, *args, **kwargs):
        translated = self._data.get(key, key)
        if args or kwargs:
            try:
                return translated.format(*args, **kwargs)
            except (KeyError, IndexError):
                return translated
        return translated


_ = I18n()
