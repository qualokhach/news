#!/usr/bin/env python3
"""Đồng bộ header/footer của AppNho vào các trang HTML của News.

Dùng khi menu/footer của appnho.io.vn thay đổi:
    python scripts/sync_appnho_shell.py                      # lấy từ https://appnho.io.vn/
    python scripts/sync_appnho_shell.py path/to/index.html   # hoặc từ file trang chủ AppNho trên máy

Script chỉ thay phần nằm giữa các dòng đánh dấu
<!-- APPNHO-SHELL:HEADER:START --> ... END và <!-- APPNHO-SHELL:FOOTER:START --> ... END
nên không đụng tới nội dung riêng của News.
"""
import re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://appnho.io.vn/"

def load(src):
    if src.startswith("http"):
        return urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "appnho-news-sync"}), timeout=30).read().decode("utf-8")
    return Path(src).read_text(encoding="utf-8")

def absolutize(html):
    def fix(m):
        u = m.group(2)
        if u.startswith(("http://", "https://", "mailto:", "tel:", "#", "javascript:")): return m.group(0)
        u = ORIGIN + (u.lstrip("/") if u.startswith("/") else ("" if u == "index.html" else u))
        return f'{m.group(1)}="{u}"'
    return re.sub(r'(href)="([^"]*)"', fix, html)

def build(home):
    header = re.search(r'<header class="site-header[^"]*">.*?</header>', home, re.S).group(0)
    footer = re.search(r'<footer class="appnho-footer">.*?</footer>', home, re.S).group(0)
    shell_js = re.search(r'<script data-appnho-shell="">.*?</script>', home, re.S).group(0)
    header = absolutize(header)
    header = re.sub(r'<header class="site-header[^"]*">', '<header class="site-header appnho-site-header">', header, 1)
    header = header.replace('<a class="active" href="https://appnho.io.vn/">', '<a href="https://appnho.io.vn/">')
    header = header.replace('<a class="nav-direct" href="https://appnho.io.vn/news/">', '<a aria-current="page" class="nav-direct active" href="https://appnho.io.vn/news/">')
    footer = absolutize(footer)
    footer = re.sub(r'©\s*\d{4}\s*AppNho\.', '© <span id="year">2026</span> AppNho.', footer, 1)
    footer = footer.replace('<a href="https://appnho.io.vn/privacy/index.html">', '<a href="about.html">Nguyên tắc biên tập</a><a href="feed.xml">RSS</a><a href="https://appnho.io.vn/privacy/index.html">', 1)
    hdr = '<div aria-hidden="true" class="nav-overlay"></div>'
    return header + "\n" + hdr, footer + "\n" + shell_js

def replace(text, tag, body):
    a, b = f"<!-- APPNHO-SHELL:{tag}:START -->", f"<!-- APPNHO-SHELL:{tag}:END -->"
    pat = re.compile(re.escape(a) + r".*?" + re.escape(b), re.S)
    assert pat.search(text), f"missing {tag} markers"
    return pat.sub(lambda _: f"{a}\n{body}\n{b}", text, 1)

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else ORIGIN
    header, footer = build(load(src))
    for p in sorted(ROOT.glob("*.html")):
        t = p.read_text(encoding="utf-8")
        t2 = replace(replace(t, "HEADER", header), "FOOTER", footer)
        if t2 != t:
            p.write_text(t2, encoding="utf-8"); print("updated", p.name)
        else:
            print("unchanged", p.name)

if __name__ == "__main__":
    main()
