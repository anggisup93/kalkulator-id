#!/usr/bin/env python3
"""Static site generator untuk KalkulatorID.

Tanpa dependency eksternal - cukup Python 3.8+.
Jalankan:  python build.py
Hasil ada di folder dist/ (siap di-deploy ke Cloudflare Pages / Netlify).
"""
import hashlib
import html
import json
import re
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
PAGES = ROOT / "pages"
PLACEHOLDER = re.compile(r"{{\s*([A-Z_]+)\s*}}")
TAG = re.compile(r"<[^>]+>")
FAQ_PAIR = re.compile(r"<h3>(.*?)</h3>\s*<p>(.*?)</p>", re.S)


def load_config():
    return json.loads((ROOT / "site.json").read_text(encoding="utf-8"))


def render(template: str, ctx: dict) -> str:
    """Substitusi {{KEY}} satu kali (nilai pengganti tidak ikut dipindai)."""
    return PLACEHOLDER.sub(lambda m: str(ctx.get(m.group(1), "")), template)


def plain(s: str) -> str:
    """Buang tag HTML + normalkan entity jadi teks biasa (untuk JSON-LD)."""
    s = TAG.sub("", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def build_nav(cfg) -> str:
    by_slug = {p["slug"]: p for p in cfg["pages"]}
    slugs = cfg.get("primary_nav") or [
        p["slug"] for p in cfg["pages"] if p.get("in_index")
    ][:5]
    links = [
        f'<a href="/{s}/">{by_slug[s]["nav"] or by_slug[s]["title"]}</a>'
        for s in slugs if s in by_slug
    ]
    links.append('<a class="nav-all" href="/alat/">Semua Alat</a>')
    return "\n    ".join(links)


def category_sections(cfg) -> str:
    """Kartu semua alat, dikelompokkan per kategori (dipakai beranda + /alat/)."""
    index_pages = [p for p in cfg["pages"] if p.get("in_index")]
    cats = []
    for p in index_pages:
        c = p.get("category") or "Lainnya"
        if c not in cats:
            cats.append(c)
    out = []
    for c in cats:
        group = [p for p in index_pages if (p.get("category") or "Lainnya") == c]
        cards = "\n".join(card_html(p) for p in group)
        out.append(
            f'<section class="cat"><h2>{c}</h2>'
            f'<div class="grid">\n{cards}\n</div></section>'
        )
    return "\n".join(out)


def analytics_tag(cfg) -> str:
    tok = cfg.get("cf_analytics_token", "").strip()
    if not tok:
        return "<!-- Cloudflare Web Analytics belum aktif: isi 'cf_analytics_token' di site.json -->"
    return (
        '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
        'data-cf-beacon=\'{"token": "' + tok + '"}\'></script>'
    )


def card_html(p) -> str:
    terms = " ".join(filter(None, [
        p["slug"], p.get("nav", ""), p.get("category", ""), p["title"],
        p["description"],
    ])).lower()
    icon = p.get("icon", "")
    ic = f'<span class="card-ic" aria-hidden="true">{icon}</span>' if icon else ""
    return (
        f'<a class="card" href="/{p["slug"]}/" data-terms="{html.escape(terms, quote=True)}">'
        f'{ic}<span class="card-tx"><h3>{p["nav"] or p["title"]}</h3>'
        f'<p>{p["description"]}</p></span></a>'
    )


def breadcrumb_html(p) -> str:
    cat = p.get("category")
    mid = f'<span>{cat}</span> <span class="sep">/</span> ' if cat else ""
    return (
        '<nav class="breadcrumb" aria-label="Breadcrumb">'
        '<a href="/">Beranda</a> <span class="sep">/</span> '
        f'{mid}<span aria-current="page">{p["nav"] or p["title"]}</span></nav>'
    )


def related_html(cfg, current) -> str:
    pool = [p for p in cfg["pages"]
            if p.get("in_index") and p["slug"] != current["slug"]]
    same = [p for p in pool if p.get("category") == current.get("category")]
    others = [p for p in pool if p not in same]
    picks = (same + others)[:3]
    if not picks:
        return ""
    cards = "\n".join(card_html(p) for p in picks)
    return (
        '<aside class="related"><h2>Kalkulator terkait</h2>'
        f'<div class="grid">\n{cards}\n</div></aside>'
    )


def jsonld_tag(data) -> str:
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def jsonld_page(cfg, p, inner, domain) -> str:
    url = f'{domain}/{p["slug"]}/'
    blocks = [{
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Beranda",
             "item": f"{domain}/"},
            {"@type": "ListItem", "position": 2,
             "name": p["nav"] or p["title"], "item": url},
        ],
    }]
    faqs = [(plain(q), plain(a)) for q, a in FAQ_PAIR.findall(inner)]
    faqs = [(q, a) for q, a in faqs if q and a]
    if faqs:
        blocks.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        })
    return "\n".join(jsonld_tag(b) for b in blocks)


def jsonld_home(cfg, domain) -> str:
    site = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": cfg["site_name"],
        "url": f"{domain}/",
        "description": cfg["tagline"],
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{domain}/?q={{search_term_string}}",
            "query-input": "required name=search_term_string",
        },
    }
    items = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1,
             "url": f'{domain}/{p["slug"]}/', "name": p["nav"] or p["title"]}
            for i, p in enumerate(x for x in cfg["pages"] if x.get("in_index"))
        ],
    }
    return jsonld_tag(site) + "\n" + jsonld_tag(items)


def adsense_head(cfg) -> str:
    client = cfg.get("adsense_client", "").strip()
    if not client:
        return "<!-- AdSense belum aktif: isi 'adsense_client' di site.json (mis. ca-pub-1234567890123456) -->"
    return (
        '<script async src="https://pagead2.googlesyndication.com/pagead/js/'
        f'adsbygoogle.js?client={client}" crossorigin="anonymous"></script>'
    )


def adsense_slot(cfg) -> str:
    client = cfg.get("adsense_client", "").strip()
    if not client:
        return ""
    return (
        f'<ins class="adsbygoogle" style="display:block" data-ad-client="{client}" '
        'data-ad-format="auto" data-full-width-responsive="true"></ins>'
        '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>'
    )


HOME_SEARCH_JS = """
<script>
(function () {
  var q = document.getElementById('cari');
  if (!q) return;
  var cards = [].slice.call(document.querySelectorAll('.card[data-terms]'));
  var cats = [].slice.call(document.querySelectorAll('.cat'));
  var kosong = document.getElementById('cari-kosong');
  function apply(s) {
    s = (s || '').trim().toLowerCase();
    var any = false;
    cards.forEach(function (c) {
      var hit = !s || c.getAttribute('data-terms').indexOf(s) > -1;
      c.hidden = !hit;
      if (hit) any = true;
    });
    cats.forEach(function (sec) {
      sec.hidden = sec.querySelectorAll('.card:not([hidden])').length === 0;
    });
    if (kosong) kosong.hidden = any;
  }
  q.addEventListener('input', function () { apply(q.value); });
  var pre = new URLSearchParams(location.search).get('q');
  if (pre) { q.value = pre; apply(pre); }
})();
</script>
"""


SW_TEMPLATE = """/* Service worker KalkulatorID - dibuat otomatis oleh build.py */
var CACHE = "__CACHE__";
var PRECACHE = __PRECACHE__;

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return c.addAll(PRECACHE);
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  e.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
        return res;
      }).catch(function () {
        if (req.mode === "navigate") return caches.match("/");
      });
    })
  );
});
"""


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    cfg = load_config()
    layout = (ROOT / "layout.html").read_text(encoding="utf-8")
    domain = cfg["domain"].rstrip("/")
    nav = build_nav(cfg)
    year = str(date.today().year)
    today = date.today().isoformat()

    # Versi build: hash dari semua sumber (aset, layout, halaman, konfigurasi).
    # Dipakai untuk cache-busting ?v= dan nama cache service worker, sehingga
    # perubahan apa pun memaksa browser + PWA mengambil versi terbaru.
    src = [(ROOT / "layout.html").read_bytes(),
           (ROOT / "site.json").read_bytes(),
           (ROOT / "assets" / "style.css").read_bytes(),
           (ROOT / "assets" / "calc.js").read_bytes(),
           (ROOT / "assets" / "icon.svg").read_bytes()]
    src += [f.read_bytes() for f in sorted(PAGES.glob("*.html"))]
    asset_ver = hashlib.sha1(b"".join(src)).hexdigest()[:8]

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "assets", DIST / "assets")

    base_ctx = {
        "NAV": nav,
        "YEAR": year,
        "SITE_NAME": cfg["site_name"],
        "ASSET_VER": asset_ver,
        "ADSENSE_HEAD": adsense_head(cfg),
        "ADSENSE_SLOT": adsense_slot(cfg),
        "ANALYTICS": analytics_tag(cfg),
        "JSONLD": "",
        "BREADCRUMB": "",
        "RELATED": "",
    }
    urls = [f"{domain}/", f"{domain}/alat/"]

    # --- Halaman per slug ---
    for p in cfg["pages"]:
        slug = p["slug"]
        inner = (PAGES / f"{slug}.html").read_text(encoding="utf-8")
        is_calc = bool(p.get("in_index"))
        ctx = {
            **base_ctx,
            "TITLE": p["title"],
            "DESCRIPTION": p["description"],
            "CANONICAL": f"{domain}/{slug}/",
            "CONTENT": inner,
            "JSONLD": jsonld_page(cfg, p, inner, domain) if is_calc else "",
            "BREADCRUMB": breadcrumb_html(p) if is_calc else "",
            "RELATED": related_html(cfg, p) if is_calc else "",
        }
        write(DIST / slug / "index.html", render(layout, ctx))
        urls.append(f"{domain}/{slug}/")

    # --- Beranda: hero + pencarian + kartu per kategori ---
    index_pages = [p for p in cfg["pages"] if p.get("in_index")]
    sections = category_sections(cfg)
    index_inner = (
        '<div class="hero">'
        f'<h1>{cfg["site_name"]}</h1>'
        f'<p class="lead">{cfg["tagline"]}</p>'
        '<input type="search" id="cari" class="search" autocomplete="off" '
        'placeholder="Cari kalkulator… (mis. KPR, BMI, umur)">'
        '</div>\n'
        + sections
        + '\n<p id="cari-kosong" class="empty" hidden>Tidak ada kalkulator yang cocok.</p>'
        + HOME_SEARCH_JS
    )
    write(DIST / "index.html", render(layout, {
        **base_ctx,
        "TITLE": f'{cfg["site_name"]} - {cfg["tagline"]}',
        "DESCRIPTION": cfg["tagline"],
        "CANONICAL": f"{domain}/",
        "CONTENT": index_inner,
        "JSONLD": jsonld_home(cfg, domain),
        "ADSENSE_SLOT": "",
    }))

    # --- /alat/ : indeks semua alat A-Z per kategori ---
    alat_inner = (
        '<nav class="breadcrumb" aria-label="Breadcrumb">'
        '<a href="/">Beranda</a> <span class="sep">/</span> '
        '<span aria-current="page">Semua Alat</span></nav>'
        '<h1>Semua Alat</h1>'
        f'<p class="lead">{len(index_pages)} kalkulator &amp; alat, dikelompokkan per kategori.</p>'
        '<input type="search" id="cari" class="search" autocomplete="off" '
        'placeholder="Cari alat…">\n'
        + sections
        + '\n<p id="cari-kosong" class="empty" hidden>Tidak ada alat yang cocok.</p>'
        + HOME_SEARCH_JS
    )
    write(DIST / "alat" / "index.html", render(layout, {
        **base_ctx,
        "TITLE": f'Semua Alat - {cfg["site_name"]}',
        "DESCRIPTION": f'Daftar lengkap {len(index_pages)} kalkulator dan alat di {cfg["site_name"]}.',
        "CANONICAL": f"{domain}/alat/",
        "CONTENT": alat_inner,
        "ADSENSE_SLOT": "",
    }))

    # --- 404 ---
    write(DIST / "404.html", render(layout, {
        **base_ctx,
        "TITLE": f'Halaman tidak ditemukan - {cfg["site_name"]}',
        "DESCRIPTION": "Halaman yang kamu cari tidak ada.",
        "CANONICAL": f"{domain}/404",
        "CONTENT": (
            '<h1>Halaman tidak ditemukan</h1>'
            '<p class="lead">Alamat yang kamu buka tidak ada atau sudah dipindah.</p>'
            '<p><a href="/">Kembali ke beranda</a> &middot; '
            '<a href="/alat/">Lihat semua alat</a></p>'
        ),
        "ADSENSE_SLOT": "",
    }))

    # --- sitemap.xml + robots.txt ---
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls]
    sm.append("</urlset>")
    write(DIST / "sitemap.xml", "\n".join(sm))
    write(DIST / "robots.txt",
          f"User-agent: *\nAllow: /\n\nSitemap: {domain}/sitemap.xml\n")

    # --- PWA: manifest + service worker (bisa dipasang & jalan offline) ---
    manifest = {
        "name": cfg["site_name"] + " - " + cfg["tagline"],
        "short_name": cfg["site_name"],
        "description": cfg["tagline"],
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f7f8fa",
        "theme_color": "#2f6bff",
        "lang": "id",
        "icons": [
            {"src": "/assets/icon.svg", "sizes": "any", "type": "image/svg+xml",
             "purpose": "any maskable"},
        ],
    }
    write(DIST / "manifest.webmanifest",
          json.dumps(manifest, ensure_ascii=False, indent=2))

    precache = ["/", "/alat/", "/manifest.webmanifest",
                f"/assets/style.css?v={asset_ver}",
                f"/assets/calc.js?v={asset_ver}",
                "/assets/icon.svg"]
    precache += [f"/{p['slug']}/" for p in cfg["pages"]]
    sw = SW_TEMPLATE.replace("__CACHE__", "kalkulatorid-" + asset_ver).replace(
        "__PRECACHE__", json.dumps(precache))
    write(DIST / "sw.js", sw)

    print(f"OK - {len(urls)} halaman dibangun ke {DIST}")
    print("Pratinjau lokal:  python -m http.server -d dist 8000")


if __name__ == "__main__":
    main()
