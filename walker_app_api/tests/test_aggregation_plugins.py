from datetime import datetime

from app.services.aggregation.plugins import deepseek as deepseek_plugin
from app.services.aggregation.plugins import huggingface as huggingface_plugin


def test_huggingface_resolves_pdf_and_github_from_paper_page(monkeypatch):
    html = """
    <html>
      <body>
        <a href="https://arxiv.org/abs/2501.12345">PDF</a>
        <script type="application/json">
          {"githubRepo":"https://github.com/acme/research-repo"}
        </script>
      </body>
    </html>
    """

    monkeypatch.setattr(huggingface_plugin, "_fetch_text_sync", lambda url: html)

    pdf_url, github_url = huggingface_plugin._resolve_links_for_paper_sync(
        "https://huggingface.co/papers/2501.12345"
    )

    assert pdf_url == "https://arxiv.org/pdf/2501.12345.pdf"
    assert github_url == "https://github.com/acme/research-repo"


def test_deepseek_fetch_repos_from_atom_parses_unique_relevant_repos(monkeypatch):
    atom_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>deepseek-ai added user to deepseek-ai/DeepSeek-V3</title>
        <link rel="alternate" href="https://github.com/deepseek-ai/DeepSeek-V3" />
      </entry>
      <entry>
        <title>deepseek-ai added user to deepseek-ai/DeepSeek-V3</title>
        <link rel="alternate" href="https://github.com/deepseek-ai/DeepSeek-V3" />
      </entry>
      <entry>
        <title>deepseek-ai added user to deepseek-ai/DeepSeek-R1</title>
        <link rel="alternate" href="https://github.com/deepseek-ai/DeepSeek-R1" />
      </entry>
      <entry>
        <title>deepseek-ai added user to deepseek-ai/not-relevant</title>
        <link rel="alternate" href="https://github.com/deepseek-ai/not-relevant" />
      </entry>
    </feed>
    """

    class DummyResponse:
        text = atom_feed

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(deepseek_plugin.httpx, "get", lambda *args, **kwargs: DummyResponse())

    repos = deepseek_plugin._fetch_repos_from_github_atom()

    assert repos == [
        {
            "title": "DeepSeek V3",
            "url": "https://github.com/deepseek-ai/DeepSeek-V3",
            "description": "",
        },
        {
            "title": "DeepSeek R1",
            "url": "https://github.com/deepseek-ai/DeepSeek-R1",
            "description": "",
        },
    ]


def test_deepseek_scrape_falls_back_to_atom_when_api_is_empty(monkeypatch):
    published_at = datetime(2026, 3, 16, 9, 30, 0)

    monkeypatch.setattr(deepseek_plugin, "_fetch_repos_from_github_api", lambda: [])
    monkeypatch.setattr(
        deepseek_plugin,
        "_fetch_repos_from_github_atom",
        lambda: [
            {
                "title": "DeepSeek V3",
                "url": "https://github.com/deepseek-ai/DeepSeek-V3",
                "description": "Open weights.",
            }
        ],
    )
    monkeypatch.setattr(
        deepseek_plugin,
        "_fetch_readme_metadata",
        lambda url, client=None: (
            published_at,
            {
                "date_iso": published_at.isoformat(),
                "date_display": "4 weeks ago",
                "readme_commit_url": f"{url}/commit/main",
            },
        ),
    )

    items = deepseek_plugin.scrape()

    assert len(items) == 1
    item = items[0]
    assert item["url"] == "https://github.com/deepseek-ai/DeepSeek-V3"
    assert item["published_at"] == published_at
    assert item["meta_data"]["extraction_method"] == "github_atom"
    assert item["meta_data"]["description"] == "Open weights."
    assert item["meta_data"]["readme_commit_url"] == "https://github.com/deepseek-ai/DeepSeek-V3/commit/main"
