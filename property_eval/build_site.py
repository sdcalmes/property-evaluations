"""Build the fully static property dashboard from reviewed JSON and Markdown."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import bleach
import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape


ROOT = Path(__file__).resolve().parent.parent
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "h1", "h2", "h3", "h4", "p", "pre", "code", "hr", "br", "table",
    "thead", "tbody", "tr", "th", "td", "del",
}
# Hashes of normalized private destination street lines. Do not commit the
# destination addresses themselves to this public repository.
PRIVATE_STREET_SHA256 = {
    "1586fb3207a4326ba4df739df0f53e0a275282162fe72a80d8f2ecf062d05c04",
    "9808cd09d4aafbdff67fe231ee63ca8437fbbbb693f1394fdddad8f4ea9fef38",
    "c4abe7a54e9be35ae7aefcc8cd9f8a0a08df098fd624c7ec444118124d5bc0cf",
}


def base_path(value: str) -> str:
    """Normalize a project path to one slash on each side."""
    if not value or value == "/":
        return "/"
    if "?" in value or "#" in value or ".." in value or "//" in value:
        raise ValueError("Invalid base path")
    return "/" + value.strip("/") + "/"


def display(value, suffix=""):
    if value is None or value == "":
        return "Unknown"
    return f"{value:,}{suffix}" if isinstance(value, (int, float)) and not isinstance(value, bool) else f"{value}{suffix}"


def money(value):
    return "Unknown" if value is None else f"${value:,.0f}"


def price_range(low, high):
    if low is None and high is None:
        return "Not assessed"
    return f"{money(low)}–{money(high)}"


def private_markers(profile):
    markers = set()
    for dest in profile["destinations"].values():
        for field in ("user_entered_address", "routing_address"):
            address = dest.get(field)
            if address:
                markers.add(address.casefold())
                # Catch street + house number even if the city/ZIP differs.
                markers.add(address.split(",")[0].casefold())
    return markers


def check_privacy(output: Path, profile: dict):
    markers = private_markers(profile)
    for file in output.rglob("*"):
        if file.is_file():
            contents = html.unescape(file.read_text(encoding="utf-8")).casefold()
            for marker in markers:
                if marker in contents:
                    raise ValueError(f"Private destination address found in generated site: {file}")
            words = re.findall(r"[a-z0-9]+", re.sub(r"<[^>]+>", " ", contents))
            for size in (3, 4):
                for i in range(len(words) - size + 1):
                    digest = hashlib.sha256(" ".join(words[i:i + size]).encode()).hexdigest()
                    if digest in PRIVATE_STREET_SHA256:
                        raise ValueError(f"Private destination address found in generated site: {file}")


def load_records(root: Path):
    records = []
    for path in sorted((root / "data/properties").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        slug = record.get("slug")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug) or slug != path.stem:
            raise ValueError(f"Invalid or mismatched slug: {path}")
        if not isinstance(record.get("address"), str) or not record["address"].strip():
            raise ValueError(f"Missing address: {path}")
        name = record.get("evaluation_markdown")
        if name != f"{slug}.md":
            raise ValueError(f"Expected evaluation_markdown: {slug}.md in {path}")
        narrative = root / "evaluations" / name
        if not narrative.is_file():
            raise ValueError(f"Missing evaluation: {narrative}")
        for key in ("status", "current_list_price", "original_list_price", "beds", "baths",
                    "year_built", "above_grade_sqft", "below_grade_finished_sqft", "garage",
                    "lot_acres", "utilities", "hoa", "annual_taxes", "buyer_fit_score",
                    "estimated_value_low", "estimated_value_high", "pricing_conclusion",
                    "evaluation_date", "listing_url", "opening_offer", "reasonable_range",
                    "caution_price", "walk_away_price"):
            record.setdefault(key, None)
        for key in ("major_positives", "major_concerns", "uncertainties"):
            record.setdefault(key, [])
            if not isinstance(record[key], list):
                raise ValueError(f"{key} must be a list in {path}")
        record.setdefault("commutes", [])
        if not isinstance(record["commutes"], list):
            raise ValueError(f"commutes must be a list in {path}")
        for trip in record.get("commutes", []):
            if "address" in trip or "routing_address" in trip:
                raise ValueError(f"Commutes may only contain destination labels and results: {path}")
        if record["listing_url"] and urlparse(record["listing_url"]).scheme not in ("https", "http"):
            raise ValueError(f"Listing URL must be HTTP(S): {path}")
        records.append((record, narrative))
    return records


def build(root=ROOT, output=None, site_base="/property-evaluations/"):
    root = Path(root)
    output = Path(output) if output else root / "_site"
    if output.resolve() == root.resolve() or (root.resolve() in output.resolve().parents and output.resolve().name != "_site"):
        # Default _site is intentionally disposable; never delete arbitrary source paths.
        raise ValueError("Output must be _site inside the repo, or an external directory")
    base = base_path(site_base)
    profile = json.loads((root / "buyer_profile.json").read_text(encoding="utf-8"))
    records = load_records(root)
    env = Environment(loader=FileSystemLoader(root / "templates"), autoescape=select_autoescape(["html"]))
    env.globals.update(base=base, display=display, money=money, price_range=price_range)

    if output.exists():
        shutil.rmtree(output)
    (output / "properties").mkdir(parents=True)
    (output / "static").mkdir()
    shutil.copyfile(root / "static/style.css", output / "static/style.css")
    (output / ".nojekyll").touch()

    cards = []
    for record, narrative in records:
        raw = markdown.markdown(narrative.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
        rendered = bleach.clean(raw, tags=ALLOWED_TAGS,
                                attributes={"a": ["href", "title"], "th": ["align"], "td": ["align"]},
                                protocols=["https", "http", "mailto"], strip=True)
        detail = output / "properties" / record["slug"]
        detail.mkdir()
        (detail / "index.html").write_text(env.get_template("property.html").render(
            property=record, evaluation=rendered), encoding="utf-8")
        cards.append(record)

    cards.sort(key=lambda r: (r.get("evaluation_date") or "", r["address"]), reverse=True)
    (output / "index.html").write_text(env.get_template("index.html").render(properties=cards), encoding="utf-8")
    try:
        check_privacy(output, profile)
    except ValueError:
        shutil.rmtree(output)
        raise
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base-path", default="/property-evaluations/")
    args = parser.parse_args()
    print(f"Built {build(output=args.output, site_base=args.base_path)}")
