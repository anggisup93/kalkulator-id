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


def load_data():
    f = ROOT / "data.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def feedback_html(cfg) -> str:
    key = (cfg.get("web3forms_key") or "").strip()
    form = ""
    if key:
        form = (
            '<form class="fb-form" hidden method="POST" action="https://api.web3forms.com/submit">'
            f'<input type="hidden" name="access_key" value="{key}">'
            '<input type="hidden" name="subject" value="Masukan KalkulatorID">'
            '<input type="hidden" name="halaman" class="fb-page" value="">'
            '<textarea name="pesan" rows="3" required '
            'placeholder="Apa yang kurang tepat atau bisa diperbaiki?"></textarea>'
            '<input type="email" name="email" placeholder="Email (opsional, jika ingin dibalas)">'
            '<button type="submit" class="btn-sec">Kirim masukan</button>'
            '</form>'
        )
    return (
        '<div class="feedback" data-noprint data-feedback>'
        '<span class="fb-q">Halaman ini membantu?</span>'
        '<span class="fb-buttons">'
        '<button type="button" class="fb-btn" data-fb="ya">&#128077; Ya</button>'
        '<button type="button" class="fb-btn" data-fb="tidak">&#128078; Kurang</button>'
        '</span>'
        '<a class="fb-link" href="/kontak/">Kirim masukan / koreksi</a>'
        f'{form}</div>'
    )


def render(template: str, ctx: dict) -> str:
    """Substitusi {{KEY}} satu kali (nilai pengganti tidak ikut dipindai)."""
    return PLACEHOLDER.sub(lambda m: str(ctx.get(m.group(1), "")), template)


def render_partial(text: str, ctx: dict) -> str:
    """Seperti render(), tapi hanya kunci yang dikenal; sisanya dibiarkan."""
    return PLACEHOLDER.sub(
        lambda m: str(ctx[m.group(1)]) if m.group(1) in ctx else m.group(0), text)


def contact_form_html(cfg) -> str:
    key = (cfg.get("web3forms_key") or "").strip()
    if not key:
        return ('<p class="art-meta">Formulir kirim langsung belum aktif. '
                'Untuk sekarang, kirim email ke alamat di atas.</p>')
    return (
        '<form id="kontak-form" class="fb-form" method="POST" '
        'action="https://api.web3forms.com/submit">'
        f'<input type="hidden" name="access_key" value="{key}">'
        '<input type="hidden" name="subject" value="Pesan dari halaman Kontak KalkulatorID">'
        '<input type="text" name="nama" placeholder="Nama (opsional)">'
        '<input type="email" name="email" placeholder="Email (jika ingin dibalas)">'
        '<textarea name="pesan" rows="5" required '
        'placeholder="Tulis masukan, koreksi rumus, atau pertanyaan Anda…"></textarea>'
        '<button type="submit" class="btn-sec">Kirim pesan</button>'
        '</form>'
        '<p id="kontak-msg" class="art-meta"></p>'
    )


def plain(s: str) -> str:
    """Buang tag HTML + normalkan entity jadi teks biasa (untuk JSON-LD)."""
    s = TAG.sub("", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def tools_json(cfg) -> str:
    """Daftar alat untuk overlay pencarian (dipakai calc.js)."""
    tools = [
        {
            "n": p["nav"] or p["title"],
            "u": f'/{p["slug"]}/',
            "c": p.get("category", "Lainnya"),
            "i": p.get("icon", ""),
            "t": " ".join(filter(None, [
                p["slug"], p.get("nav", ""), p.get("category", ""),
                p["title"], p["description"],
            ])).lower(),
        }
        for p in cfg["pages"] if p.get("in_index")
    ]
    return json.dumps(tools, ensure_ascii=False, separators=(",", ":"))


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


def coming_soon_section(cfg) -> str:
    """Kartu 'Segera Hadir' (tidak bisa diklik) untuk alat yang sedang disiapkan."""
    items = cfg.get("coming_soon") or []
    if not items:
        return ""
    cards = "\n".join(
        f'<div class="card card-soon" aria-disabled="true">'
        f'<span class="card-ic" aria-hidden="true">{it.get("icon", "")}</span>'
        f'<span class="card-tx"><h3>{it["name"]} '
        f'<span class="badge-soon">Segera</span></h3>'
        f'<p>{it.get("note", "")}</p></span></div>'
        for it in items
    )
    return (
        '<section class="cat cat-soon"><h2>Segera Hadir</h2>'
        f'<div class="grid">\n{cards}\n</div></section>'
    )


def analytics_tag(cfg) -> str:
    tok = cfg.get("cf_analytics_token", "").strip()
    if not tok:
        return "<!-- Cloudflare Web Analytics belum aktif: isi 'cf_analytics_token' di site.json -->"
    # Muat beacon hanya di produksi (https, bukan localhost) agar dev bersih.
    return (
        "<script>if(location.protocol===\"https:\"&&!/^(localhost|127\\.|\\[?::1)/.test(location.hostname)){"
        "var s=document.createElement(\"script\");s.defer=true;"
        "s.src=\"https://static.cloudflareinsights.com/beacon.min.js\";"
        "s.setAttribute(\"data-cf-beacon\",'{\"token\":\"" + tok + "\"}');"
        "document.head.appendChild(s);}</script>"
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


def load_articles():
    f = ROOT / "articles.json"
    if not f.exists():
        return []
    arts = json.loads(f.read_text(encoding="utf-8"))
    return sorted(arts, key=lambda a: a.get("date", ""), reverse=True)


def crumbs(trail) -> str:
    """trail: list of (nama, href|None). href None = halaman aktif."""
    parts = []
    for name, href in trail:
        if href:
            parts.append(f'<a href="{href}">{name}</a>')
        else:
            parts.append(f'<span aria-current="page">{name}</span>')
    return ('<nav class="breadcrumb" aria-label="Breadcrumb">'
            + ' <span class="sep">/</span> '.join(parts) + '</nav>')


def related_slugs_html(cfg, slugs) -> str:
    by = {p["slug"]: p for p in cfg["pages"]}
    picks = [by[s] for s in slugs if s in by]
    if not picks:
        return ""
    cards = "\n".join(card_html(p) for p in picks)
    return ('<aside class="related"><h2>Kalkulator terkait</h2>'
            f'<div class="grid">\n{cards}\n</div></aside>')


def jsonld_article(a, inner, domain, site_name) -> str:
    url = f'{domain}/panduan/{a["slug"]}/'
    org = {"@type": "Organization", "name": site_name}
    blocks = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "Beranda", "item": f"{domain}/"},
             {"@type": "ListItem", "position": 2, "name": "Panduan", "item": f"{domain}/panduan/"},
             {"@type": "ListItem", "position": 3, "name": a["title"], "item": url},
         ]},
        {"@context": "https://schema.org", "@type": "Article",
         "headline": a["title"], "description": a["description"],
         "datePublished": a.get("date"),
         "dateModified": a.get("updated") or a.get("date"),
         "author": org, "publisher": org, "mainEntityOfPage": url},
    ]
    faqs = [(plain(q), plain(ans)) for q, ans in FAQ_PAIR.findall(inner)]
    faqs = [(q, ans) for q, ans in faqs if q and ans]
    if faqs:
        blocks.append({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": ans}}
                for q, ans in faqs
            ],
        })
    return "\n".join(jsonld_tag(b) for b in blocks)


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
    # Unit iklan manual hanya dipasang bila 'adsense_slot_id' diisi (setelah
    # akun disetujui & unit iklan dibuat di AdSense). Selama peninjauan cukup
    # skrip verifikasi di <head>; tanpa slot id jangan render kotak kosong.
    client = cfg.get("adsense_client", "").strip()
    slot = cfg.get("adsense_slot_id", "").strip()
    if not client or not slot:
        return ""
    return (
        f'<ins class="adsbygoogle" style="display:block" data-ad-client="{client}" '
        f'data-ad-slot="{slot}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
        '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>'
    )


HOME_SEARCH_JS = """
<script>
(function () {
  var q = document.getElementById('cari');
  if (!q) return;
  var cards = [].slice.call(document.querySelectorAll('.card[data-terms]'));
  var cats = [].slice.call(document.querySelectorAll('.cat:not(.cat-soon)'));
  var kosong = document.getElementById('cari-kosong');
  var soon = [].slice.call(document.querySelectorAll('.cat-soon'));
  function apply(s) {
    s = (s || '').trim().toLowerCase();
    var any = false;
    cards.forEach(function (c) {
      var hit = !s || c.getAttribute('data-terms').indexOf(s) > -1;
      c.hidden = !hit;
      if (hit) any = true;
    });
    cats.forEach(function (sec) {
      sec.hidden = sec.querySelectorAll('.card[data-terms]:not([hidden])').length === 0;
    });
    soon.forEach(function (sec) { sec.hidden = !!s; });
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
    year = str(date.today().year)
    today = date.today().isoformat()
    articles = load_articles()
    ART = ROOT / "articles"
    data = load_data()
    feedback = feedback_html(cfg)

    # Versi build: hash dari semua sumber (aset, layout, halaman, konfigurasi).
    # Dipakai untuk cache-busting ?v= dan nama cache service worker, sehingga
    # perubahan apa pun memaksa browser + PWA mengambil versi terbaru.
    src = [(ROOT / "layout.html").read_bytes(),
           (ROOT / "site.json").read_bytes(),
           (ROOT / "assets" / "style.css").read_bytes(),
           (ROOT / "assets" / "calc.js").read_bytes(),
           (ROOT / "assets" / "icon.svg").read_bytes()]
    src += [f.read_bytes() for f in sorted(PAGES.glob("*.html"))]
    if (ROOT / "articles.json").exists():
        src.append((ROOT / "articles.json").read_bytes())
    if (ROOT / "data.json").exists():
        src.append((ROOT / "data.json").read_bytes())
    if ART.exists():
        src += [f.read_bytes() for f in sorted(ART.glob("*.html"))]
    asset_ver = hashlib.sha1(b"".join(src)).hexdigest()[:8]

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "assets", DIST / "assets")

    base_ctx = {
        "YEAR": year,
        "SITE_NAME": cfg["site_name"],
        "ASSET_VER": asset_ver,
        "TOOLS_JSON": tools_json(cfg),
        "DATA_JSON": json.dumps(
            {k: v for k, v in data.items() if not k.startswith("_")},
            ensure_ascii=False, separators=(",", ":")),
        "ADSENSE_HEAD": adsense_head(cfg),
        "ADSENSE_SLOT": adsense_slot(cfg),
        "ANALYTICS": analytics_tag(cfg),
        "JSONLD": "",
        "BREADCRUMB": "",
        "RELATED": "",
        "FEEDBACK": "",
        "BODYCLASS": "",
    }
    urls = [f"{domain}/", f"{domain}/alat/"]

    # --- Halaman per slug ---
    zk = data.get("zakat", {})
    page_tokens = {
        "CONTACTFORM": contact_form_html(cfg),
        "SITE_NAME": cfg["site_name"],
        "TAHUN": str(data.get("tahun_berlaku", year)),
        "HARGA_EMAS": str(zk.get("harga_emas_per_gram", 1350000)),
        "HARGA_BERAS": str(zk.get("harga_beras_per_kg", 15000)),
    }
    for p in cfg["pages"]:
        slug = p["slug"]
        inner = render_partial(
            (PAGES / f"{slug}.html").read_text(encoding="utf-8"), page_tokens)
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
            "FEEDBACK": feedback if is_calc else "",
        }
        write(DIST / slug / "index.html", render(layout, ctx))
        urls.append(f"{domain}/{slug}/")

    # --- Beranda: hero + pencarian + kartu per kategori ---
    index_pages = [p for p in cfg["pages"] if p.get("in_index")]
    sections = category_sections(cfg) + "\n" + coming_soon_section(cfg)
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
        "BODYCLASS": "page-wide",
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
        "BODYCLASS": "page-wide",
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

    # --- Panduan (artikel penjelasan + referensi) ---
    for a in articles:
        body = (ART / f'{a["slug"]}.html').read_text(encoding="utf-8")
        art_inner = (
            crumbs([("Beranda", "/"), ("Panduan", "/panduan/"), (a["title"], None)])
            + f'<h1>{a["title"]}</h1>'
            + f'<p class="art-meta">Diperbarui {a.get("updated") or a.get("date", "")}</p>'
            + f'<div class="article">{body}</div>'
            + related_slugs_html(cfg, a.get("related", []))
        )
        write(DIST / "panduan" / a["slug"] / "index.html", render(layout, {
            **base_ctx,
            "TITLE": f'{a["title"]} - {cfg["site_name"]}',
            "DESCRIPTION": a["description"],
            "CANONICAL": f'{domain}/panduan/{a["slug"]}/',
            "CONTENT": art_inner,
            "JSONLD": jsonld_article(a, body, domain, cfg["site_name"]),
            "FEEDBACK": feedback,
            "ADSENSE_SLOT": "",
        }))
        urls.append(f'{domain}/panduan/{a["slug"]}/')

    if articles:
        cards = "\n".join(
            f'<a class="card" href="/panduan/{a["slug"]}/"><span class="card-tx">'
            f'<h3>{a["title"]}</h3><p>{a["description"]}</p></span></a>'
            for a in articles
        )
        pand_inner = (
            crumbs([("Beranda", "/"), ("Panduan", None)])
            + "<h1>Panduan</h1>"
            + '<p class="lead">Artikel penjelasan cara menghitung dan istilah keuangan.</p>'
            + f'<div class="grid">\n{cards}\n</div>'
        )
        write(DIST / "panduan" / "index.html", render(layout, {
            **base_ctx,
            "TITLE": f'Panduan - {cfg["site_name"]}',
            "DESCRIPTION": f'Kumpulan artikel panduan dan penjelasan dari {cfg["site_name"]}.',
            "CANONICAL": f"{domain}/panduan/",
            "CONTENT": pand_inner,
            "ADSENSE_SLOT": "",
        }))
        urls.append(f"{domain}/panduan/")

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
    if articles:
        precache.append("/panduan/")
        precache += [f'/panduan/{a["slug"]}/' for a in articles]
    sw = SW_TEMPLATE.replace("__CACHE__", "kalkulatorid-" + asset_ver).replace(
        "__PRECACHE__", json.dumps(precache))
    write(DIST / "sw.js", sw)

    print(f"OK - {len(urls)} halaman dibangun ke {DIST}")
    print("Pratinjau lokal:  python -m http.server -d dist 8000")


if __name__ == "__main__":
    main()
