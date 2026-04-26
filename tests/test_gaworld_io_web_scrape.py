"""Tests for the extracted ``gaworld.io.web_scrape`` module."""

from __future__ import annotations

import unittest

from gaworld.io.web_scrape import (
    extract_meta_description,
    extract_news_main_content,
    extract_title,
    normalize_text,
    strip_html,
)


HTML_PAGE = """
<html>
  <head>
    <title>  Sample Title  </title>
    <meta name="description" content="A short summary." />
    <meta property="og:description" content="OG fallback summary." />
  </head>
  <body>
    <script>var leak = 'should not appear';</script>
    <article>
      <p>This first paragraph is long enough to survive the length filter and should be kept.</p>
      <p>Second paragraph also exceeds the minimum length so it stays in the cleaned output too.</p>
      <p>Third paragraph confirms multiple paragraphs are joined with newlines as expected.</p>
      <p>Fourth paragraph adds enough text to comfortably exceed the 180-character article threshold.</p>
    </article>
  </body>
</html>
"""

HTML_LD_JSON = """
<html><head>
  <script type="application/ld+json">
  {
    "@type": "NewsArticle",
    "articleBody": "%s"
  }
  </script>
</head></html>
""" % ("Article body text. " * 30)


class TestStripAndNormalize(unittest.TestCase):
    def test_strip_html_removes_scripts_and_tags(self):
        cleaned = strip_html("<p>foo<script>x()</script>bar</p>")
        # Adjacent text nodes get separated by a single space; scripts removed.
        self.assertNotIn("script", cleaned)
        self.assertIn("foo", cleaned)
        self.assertIn("bar", cleaned)

    def test_strip_html_returns_empty_for_falsy(self):
        self.assertEqual("", strip_html(""))
        self.assertEqual("", strip_html(None))  # type: ignore[arg-type]

    def test_normalize_text_collapses_whitespace_and_unescapes(self):
        out = normalize_text("Hello&nbsp;&amp;\tworld\n\n!")
        self.assertIn("Hello", out)
        self.assertIn("&", out)
        self.assertIn("world", out)
        self.assertNotIn("\t", out)
        self.assertNotIn("\n\n", out)


class TestExtractTitle(unittest.TestCase):
    def test_finds_and_normalizes_title(self):
        self.assertEqual("Sample Title", extract_title(HTML_PAGE))

    def test_returns_empty_when_missing(self):
        self.assertEqual("", extract_title("<html><body>no head</body></html>"))


class TestExtractMetaDescription(unittest.TestCase):
    def test_prefers_first_match(self):
        self.assertEqual(
            "A short summary.",
            extract_meta_description(HTML_PAGE, "description", "og:description"),
        )

    def test_falls_back_to_secondary(self):
        # Only og:description is present.
        html = '<meta property="og:description" content="OG only" />'
        self.assertEqual("OG only", extract_meta_description(html, "description", "og:description"))


class TestExtractNewsMainContent(unittest.TestCase):
    def test_article_tag_extracted(self):
        out = extract_news_main_content(HTML_PAGE)
        self.assertIn("first paragraph", out)
        self.assertIn("Second paragraph", out)

    def test_ld_json_article_body_extracted(self):
        out = extract_news_main_content(HTML_LD_JSON)
        self.assertIn("Article body text.", out)


if __name__ == "__main__":
    unittest.main()
