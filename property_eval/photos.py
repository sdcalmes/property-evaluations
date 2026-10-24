"""Discover public listing images, download/validate, and build numbered review sheets."""
import argparse
import hashlib
import io
import json
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from .research_io import fetch_bytes, now, write_json


class Images(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.images, self.json_script = base, [], None

    def add(self, value, alt=''):
        if isinstance(value, dict):
            value = value.get('url') or value.get('contentUrl')
        if isinstance(value, list):
            for item in value:
                self.add(item, alt)
        elif isinstance(value, str) and value:
            url = urljoin(self.base, unescape(value))
            if urlsplit(url).scheme in ('http', 'https'):
                self.images.append({'src': url, 'alt': alt})

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img':
            # Prefer lazy/high-resolution candidates, not initial blank placeholders.
            candidates = attrs.get('data-srcset') or attrs.get('srcset')
            if candidates:
                entries = [entry.strip().split() for entry in candidates.split(',')]
                def size(entry):
                    try:
                        return float(entry[1].rstrip('wx'))
                    except (IndexError, ValueError):
                        return 0
                self.add(max(entries, key=size)[0], attrs.get('alt', ''))
            else:
                self.add(attrs.get('data-src') or attrs.get('src'), attrs.get('alt', ''))
        if tag == 'meta' and attrs.get('property') == 'og:image':
            self.add(attrs.get('content'))
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.json_script = ''

    def handle_data(self, data):
        if self.json_script is not None:
            self.json_script += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.json_script is not None:
            try:
                self.walk(json.loads(self.json_script))
            except ValueError:
                pass
            self.json_script = None

    def walk(self, value):
        if isinstance(value, dict):
            if 'image' in value:
                self.add(value['image'])
            for nested in value.values():
                self.walk(nested)
        elif isinstance(value, list):
            for nested in value:
                self.walk(nested)


def discover(html, base):
    parser = Images(base)
    parser.feed(html)
    seen, result = set(), []
    for item in parser.images:
        if item['src'] not in seen:
            seen.add(item['src'])
            result.append(item)
    return result


def download(manifest, output, import_dir=None, captured_at=None, refresh=False):
    from PIL import Image
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    previous_path = output / 'download-manifest.json'
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {'images': []}
    by_url = {item['source_url']: item for item in previous['images'] if item.get('status') == 'ok'}
    if not manifest.get('images'):
        raise ValueError('No images in manifest; inspect gallery discovery before downloading')
    if import_dir and not captured_at:
        raise ValueError('Browser imports require actual --captured-at timestamp')
    results = [{**by_url.get(source['src'], {}), 'number': i, 'source_url': source['src'],
                'status': by_url.get(source['src'], {}).get('status', 'pending')}
               for i, source in enumerate(manifest['images'], 1)]
    seen = set()
    for number, source in enumerate(manifest['images'], 1):
        url = source['src']
        record = {'number': number, 'source_url': url, 'alt': source.get('alt', '')}
        try:
            prior = by_url.get(url)
            local_files = list(Path(import_dir).glob(f'{number:03d}.*')) if import_dir else []
            if import_dir:
                if len(local_files) != 1:
                    raise ValueError(f'Expected one browser image named {number:03d}.*; got {len(local_files)}')
                raw = local_files[0].read_bytes()
                image_captured_at = captured_at
            elif prior and not refresh and (output / prior['file']).exists():
                raw = (output / prior['file']).read_bytes()
                if hashlib.sha256(raw).hexdigest() != prior['sha256']:
                    raise ValueError('Cached photo hash mismatch')
                image_captured_at = prior['captured_at']
            else:
                raw, _ = fetch_bytes(url)
                image_captured_at = now()
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()  # HTML/access walls and corrupt downloads fail here.
            with Image.open(io.BytesIO(raw)) as image:
                width, height = image.size
                extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif'}.get(image.format)
            if not extension:
                raise ValueError('Unsupported raster image format')
            digest = hashlib.sha256(raw).hexdigest()
            filename = f'{number:03d}-{digest[:12]}.{extension}'
            (output / filename).write_bytes(raw)
            record.update(status='ok', file=filename, captured_at=image_captured_at, sha256=digest,
                          width=width, height=height, thumbnail_only=max(width, height) < 900,
                          duplicate_content=digest in seen)
            seen.add(digest)
        except (OSError, RuntimeError, ValueError) as exc:
            record.update(status='failed', error=str(exc))
        results[number - 1] = record
        write_json(previous_path, {'listing_url': manifest.get('listing_url'), 'images': results})
    return results


def review(output, columns=4, rows=3):
    from PIL import Image, ImageDraw, ImageOps
    output = Path(output)
    data = json.loads((output / 'download-manifest.json').read_text())
    images = [item for item in data['images'] if item['status'] == 'ok']
    links = []
    for start in range(0, len(images), columns * rows):
        sheet = Image.new('RGB', (columns * 330, rows * 250), 'white')
        draw = ImageDraw.Draw(sheet)
        for position, item in enumerate(images[start:start + columns * rows]):
            x, y = position % columns * 330, position // columns * 250
            with Image.open(output / item['file']) as source:
                thumb = ImageOps.contain(ImageOps.exif_transpose(source).convert('RGB'), (320, 218))
                sheet.paste(thumb, (x + (330 - thumb.width) // 2, y))
            draw.text((x + 5, y + 222), f"{item['number']:02d} | {item['width']}x{item['height']}" + (' THUMBNAIL' if item['thumbnail_only'] else ''), fill='black')
        filename = f'contact-{start // (columns * rows) + 1:02d}.jpg'
        sheet.save(output / filename, quality=90)
        links.append(f'<a href="{filename}"><img src="{filename}" width="1000" alt="Numbered contact sheet"></a>')
    for item in data['images']:
        caption = f"{item['number']:02d} — {escape(item.get('alt', ''))}"
        links.append(f'<p>{caption}: {escape(item["status"])}</p>')
        if item['status'] == 'ok':
            links.append(f'<a href="{escape(item["file"], quote=True)}"><img src="{escape(item["file"], quote=True)}" style="max-width:100%" alt="{caption}"></a>')
        links.append(f'<p><a href="{escape(item["source_url"], quote=True)}">Original source</a></p>')
    (output / 'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Listing photo review</title><h1>Listing photo review</h1><p>Images are evidence to inspect, not proof of condition or renovation dates.</p>' + '\n'.join(links))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    find = sub.add_parser('discover')
    find.add_argument('--url', required=True)
    find.add_argument('--html', help='Saved rendered HTML; avoids a network request')
    find.add_argument('--out', required=True)
    get = sub.add_parser('download')
    get.add_argument('--manifest', required=True)
    get.add_argument('--refresh', action='store_true', help='Refetch images instead of reusing validated downloads')
    get.add_argument('--out', required=True)
    get.add_argument('--import-dir', help='Browser image files named 001.*, 002.* matching manifest order')
    get.add_argument('--captured-at', help='Actual ISO UTC timestamp for these browser downloads')
    show = sub.add_parser('review')
    show.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.command == 'discover':
        html = Path(args.html).read_text() if args.html else fetch_bytes(args.url)[0].decode('utf-8', errors='replace')
        images = discover(html, args.url)
        write_json(args.out, {'listing_url': args.url, 'discovered_at': now(), 'images': images,
                              'review_required': 'Filter ads/logos/unrelated properties; verify gallery count and ordering before download.'})
        print(f'{len(images)} candidates; review manifest before download')
    elif args.command == 'download':
        if args.import_dir:
            from datetime import datetime
            if not args.captured_at or datetime.fromisoformat(args.captured_at.replace('Z', '+00:00')).tzinfo is None:
                parser.error('Browser imports require actual timezone-qualified --captured-at')
        items = download(json.loads(Path(args.manifest).read_text()), args.out, args.import_dir, args.captured_at, args.refresh)
        failed = sum(item['status'] != 'ok' for item in items)
        print(f'{len(items) - failed}/{len(items)} downloaded and validated')
        if failed:
            raise SystemExit(2)
    else:
        review(args.out)
        print(str(Path(args.out) / 'review.html'))


if __name__ == '__main__':
    main()
