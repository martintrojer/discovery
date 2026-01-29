"""Unit tests for HTML scrapers."""

from pathlib import Path

from discovery.scrapers.netflix_html import convert_html_to_csv, parse_netflix_ratings_html


def test_parse_netflix_html() -> None:
    html_content = """
<ul class="structural retable stdHeight">
  <li class="retableRow">
    <div class="col date nowrap">08/1/26</div>
    <div class="col title"><a href="/title/81438325">Death by Lightning</a></div>
    <div class="col rating nowrap">
      <div>
        <button aria-label="Already rated: thumbs up (click to remove rating)" data-rating="2"></button>
      </div>
    </div>
  </li>
</ul>
"""
    rows = parse_netflix_ratings_html(html_content)
    assert len(rows) == 1
    assert rows[0]["Title"] == "Death by Lightning"
    assert rows[0]["Date"] == "2026-01-08"
    assert rows[0]["Rating"] == "thumbs up"


def test_convert_html_to_csv(tmp_path: Path) -> None:
    html_content = """
<ul class="structural retable stdHeight">
  <li class="retableRow">
    <div class="col date nowrap">17/1/26</div>
    <div class="col title"><a href="/title/81713296">The Holdovers</a></div>
    <div class="col rating nowrap">
      <div>
        <button aria-label="Already rated: two thumbs up (click to remove rating)" data-rating="3"></button>
      </div>
    </div>
  </li>
</ul>
"""
    html_path = tmp_path / "ratings.html"
    html_path.write_text(html_content)
    csv_path = tmp_path / "ratings.csv"

    rows = convert_html_to_csv(html_path, csv_path)

    assert len(rows) == 1
    content = csv_path.read_text()
    assert "Title,Date,Rating" in content
    assert "The Holdovers" in content
