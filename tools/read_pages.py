#!/usr/bin/env python3
"""Print web pages as readable text, for reading terms that matter.

The sandbox this project is developed in cannot reach mapillary.com, and a
decision about whether two hundred panoramas may be downloaded, adapted and
re-hosted is not one to take from a search-result summary. So the pages are
fetched on a runner and printed whole.

A text browser was tried first and was bounced to a Facebook "update your
browser" interstitial: mapillary.com/terms is a Meta-hosted page that renders
its text in JavaScript. A terms page that will not show a text browser its
terms has to be read with a real engine.

Printed whole, never summarised. The clause that matters is never the headline.

    python tools/read_pages.py https://www.mapillary.com/terms
    python tools/read_pages.py --file urls.txt
"""
import argparse
import sys


def read(urls, timeout_ms=60_000):
    from playwright.sync_api import sync_playwright

    failures = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for url in urls:
            print("\n" + "=" * 68)
            print(f"  {url}")
            print("=" * 68)
            try:
                # Not networkidle. A help centre that keeps a connection open
                # never goes idle, so waiting for idle waits for the timeout
                # and then reports the page as unreadable -- which is a
                # different thing from a page that would not load.
                page.goto(url, wait_until="domcontentloaded",
                          timeout=timeout_ms)
                page.wait_for_timeout(3000)         # let the text render
                text = page.inner_text("body")
            except Exception as exc:                        # noqa: BLE001
                print(f"  !! could not read: {exc}")
                failures += 1
                continue
            if not text.strip():
                print("  !! the page rendered empty")
                failures += 1
                continue
            print(text)
        browser.close()
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--file", help="a file of URLs, one per line")
    args = ap.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            urls += [ln.strip() for ln in fh if ln.strip()]
    if not urls:
        print("nothing to read", file=sys.stderr)
        return 1
    # A page that failed is worth an exit code: a reading that quietly read
    # nothing looks exactly like a reading that found nothing to object to.
    return 1 if read(urls) else 0


if __name__ == "__main__":
    raise SystemExit(main())
