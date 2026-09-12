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
from datetime import date, datetime
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
            '<input type="checkbox" name="botcheck" tabindex="-1" autocomplete="off" '
            'style="display:none !important" aria-hidden="true">'
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
        '<input type="checkbox" name="botcheck" tabindex="-1" autocomplete="off" '
        'style="display:none !important" aria-hidden="true">'
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


def cat_slug(name: str) -> str:
    """Nama kategori -> slug anchor, mis. 'Teks & Web' -> 'teks-dan-web'."""
    s = (name or "lainnya").lower().replace("&", " dan ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "lainnya"


def category_order(cfg):
    """Daftar (nama, slug, jumlah) kategori sesuai urutan kemunculan."""
    index_pages = [p for p in cfg["pages"] if p.get("in_index")]
    cats = []
    for p in index_pages:
        c = p.get("category") or "Lainnya"
        if c not in cats:
            cats.append(c)
    return [(c, cat_slug(c),
             sum(1 for p in index_pages if (p.get("category") or "Lainnya") == c))
            for c in cats]


def catnav_html(cfg) -> str:
    """Menu 'Kategori' di header: dropdown CSS, fallback ke /alat/ saat disentuh."""
    links = "\n".join(
        f'<a role="menuitem" href="/alat/#{slug}">{name}'
        f'<span class="submenu-n">{n}</span></a>'
        for name, slug, n in category_order(cfg)
    )
    return (
        '<div class="nav-item has-menu">'
        '<a class="nav-link" href="/alat/" aria-haspopup="true">Kategori</a>'
        f'<div class="submenu" role="menu">\n{links}\n</div>'
        '</div>'
    )


def category_sections(cfg) -> str:
    """Kartu semua alat, dikelompokkan per kategori (dipakai beranda + /alat/)."""
    index_pages = [p for p in cfg["pages"] if p.get("in_index")]
    out = []
    for c, slug, _ in category_order(cfg):
        group = [p for p in index_pages if (p.get("category") or "Lainnya") == c]
        cards = "\n".join(card_html(p) for p in group)
        out.append(
            f'<section class="cat" id="{slug}"><h2>{c}</h2>'
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
        f'<span class="card-ic" aria-hidden="true">{icon_html(it.get("icon", ""))}</span>'
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


def icon_html(icon_id: str, size: int = 20) -> str:
    """Ikon SVG dari sprite ICON_SPRITE (lihat definisi di bawah)."""
    if not icon_id:
        return ""
    return (
        f'<svg class="ic" width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f'<use href="#ic-{icon_id}"/></svg>'
    )


def card_html(p) -> str:
    terms = " ".join(filter(None, [
        p["slug"], p.get("nav", ""), p.get("category", ""), p["title"],
        p["description"],
    ])).lower()
    ic = (f'<span class="card-ic" aria-hidden="true">{icon_html(p.get("icon", ""))}</span>'
          if p.get("icon") else "")
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


def publisher_node(cfg, domain):
    """Entitas pengelola situs untuk JSON-LD (author/publisher)."""
    pub = cfg.get("publisher") or {}
    node = {
        "@type": pub.get("type", "Organization"),
        "name": pub.get("name") or cfg["site_name"],
        "url": f"{domain}/tentang/",
    }
    if pub.get("email"):
        node["email"] = pub["email"]
    if pub.get("area"):
        node["areaServed"] = pub["area"]
    return node


# Kategori alat -> applicationCategory schema.org
APP_CATEGORY = {
    "Keuangan": "FinanceApplication",
    "Bisnis": "FinanceApplication",
    "Kesehatan": "HealthApplication",
    "Pendidikan": "EducationApplication",
}


def org_node(cfg, domain):
    """Situs sebagai Organization + logo (dipakai publisher Article)."""
    return {
        "@type": "Organization",
        "name": cfg["site_name"],
        "url": f"{domain}/",
        "logo": {"@type": "ImageObject", "url": f"{domain}/assets/logo.png"},
    }


def jsonld_itemlist(cfg, domain):
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1,
             "url": f'{domain}/{p["slug"]}/', "name": p["nav"] or p["title"]}
            for i, p in enumerate(x for x in cfg["pages"] if x.get("in_index"))
        ],
    }


def jsonld_webapp(cfg, p, domain):
    """WebApplication: menandai halaman sebagai alat online gratis."""
    return {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": p["title"],
        "url": f'{domain}/{p["slug"]}/',
        "description": p["description"],
        "applicationCategory": APP_CATEGORY.get(p.get("category"), "UtilitiesApplication"),
        "operatingSystem": "Web",
        "browserRequirements": "Requires JavaScript",
        "inLanguage": "id-ID",
        "isAccessibleForFree": True,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "IDR"},
        "publisher": org_node(cfg, domain),
    }


def jsonld_article(a, inner, domain, site_name, cfg=None) -> str:
    url = f'{domain}/panduan/{a["slug"]}/'
    author = (publisher_node(cfg, domain) if cfg
              else {"@type": "Organization", "name": site_name})
    publisher = org_node(cfg, domain) if cfg else {"@type": "Organization", "name": site_name}
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
         "inLanguage": "id-ID", "articleSection": "Panduan",
         "author": author, "publisher": publisher, "mainEntityOfPage": url},
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
    blocks = [jsonld_webapp(cfg, p, domain), {
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


def jsonld_about(cfg, domain) -> str:
    pub = publisher_node(cfg, domain)
    about = {
        "@context": "https://schema.org",
        "@type": "AboutPage",
        "url": f"{domain}/tentang/",
        "name": f'Tentang {cfg["site_name"]}',
        "publisher": pub,
        "mainEntity": pub,
    }
    pub_block = dict(pub)
    pub_block["@context"] = "https://schema.org"
    return jsonld_tag(about) + "\n" + jsonld_tag(pub_block)


def jsonld_home(cfg, domain) -> str:
    pub = publisher_node(cfg, domain)
    site = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": cfg["site_name"],
        "url": f"{domain}/",
        "description": cfg["tagline"],
        "publisher": pub,
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{domain}/?q={{search_term_string}}",
            "query-input": "required name=search_term_string",
        },
    }
    site["inLanguage"] = "id-ID"
    pub_block = dict(pub)
    pub_block["@context"] = "https://schema.org"
    return "\n".join(jsonld_tag(b) for b in
                     (site, pub_block, jsonld_itemlist(cfg, domain)))


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


# Sprite ikon garis (Feather-style, viewBox 0 0 24 24) dipakai lewat <use href="#ic-...">
# di kartu alat, kartu "Segera Hadir", dan hasil pencarian. Warna & ketebalan
# garis diatur di elemen <svg> pemanggil (lihat icon_html()), bukan di sini.
ICON_SPRITE = """<svg style="display:none" aria-hidden="true">
<symbol id="ic-home" viewBox="0 0 24 24"><path d="M4 11 12 4l8 7"/><path d="M6 10v9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-9"/><path d="M10 20v-5h4v5"/></symbol>
<symbol id="ic-trend-up" viewBox="0 0 24 24"><polyline points="4 16 10 10 14 13 20 6"/><polyline points="14 6 20 6 20 12"/></symbol>
<symbol id="ic-tag" viewBox="0 0 24 24"><path d="M3 12 12 3h7a2 2 0 0 1 2 2v7l-9 9a2 2 0 0 1-3 0l-6-6a2 2 0 0 1 0-3z"/><circle cx="16.5" cy="7.5" r="1.3"/></symbol>
<symbol id="ic-wallet" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h13a1 1 0 0 1 1 1v3"/><rect x="3" y="7" width="18" height="12" rx="2"/><circle cx="16" cy="13" r="1.4"/></symbol>
<symbol id="ic-car" viewBox="0 0 24 24"><path d="M4 16v-4l2-5h12l2 5v4"/><path d="M4 16h16"/><circle cx="7.5" cy="16.5" r="1.6"/><circle cx="16.5" cy="16.5" r="1.6"/></symbol>
<symbol id="ic-scale" viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M7 21h10"/><path d="M4 7h6M14 7h6"/><path d="M4 7l-2.5 5a2.5 2.5 0 0 0 5 0z"/><path d="M20 7l-2.5 5a2.5 2.5 0 0 0 5 0z"/></symbol>
<symbol id="ic-flame" viewBox="0 0 24 24"><path d="M12 2c1 4-4 5-4 9a4 4 0 0 0 8 0c0-2-1-3-1-3s2 1 2 4a6 6 0 0 1-12 0C5 7 9 6 12 2z"/></symbol>
<symbol id="ic-cake" viewBox="0 0 24 24"><path d="M4 21h16v-6a3 3 0 0 0-3-3H7a3 3 0 0 0-3 3z"/><path d="M4 17h16"/><path d="M9 12V9M12 12V9M15 12V9"/><path d="M9 6c0-1 .8-1.6.5-3M12 6c0-1 .8-1.6.5-3M15 6c0-1 .8-1.6.5-3"/></symbol>
<symbol id="ic-hourglass" viewBox="0 0 24 24"><path d="M6 2h12M6 22h12"/><path d="M7 2v4a5 5 0 0 0 5 5 5 5 0 0 0 5-5V2"/><path d="M7 22v-4a5 5 0 0 1 5-5 5 5 0 0 1 5 5v4"/></symbol>
<symbol id="ic-dial" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 12V4"/><path d="M12 12l6 3"/><circle cx="12" cy="12" r="1.4"/></symbol>
<symbol id="ic-type" viewBox="0 0 24 24"><path d="M6 5h12"/><path d="M12 5v14"/><path d="M9 19h6"/></symbol>
<symbol id="ic-ruler" viewBox="0 0 24 24"><path d="M3 16 16 3l5 5-13 13z"/><path d="M13.5 5.5l2 2M9.5 9.5l2 2M5.5 13.5l2 2"/></symbol>
<symbol id="ic-list" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h10"/></symbol>
<symbol id="ic-chat" viewBox="0 0 24 24"><path d="M4 5h16v11H9l-4 4v-4H4z"/></symbol>
<symbol id="ic-percent" viewBox="0 0 24 24"><circle cx="7" cy="7" r="2.3"/><circle cx="17" cy="17" r="2.3"/><path d="M18 6 6 18"/></symbol>
<symbol id="ic-receipt" viewBox="0 0 24 24"><path d="M6 3h12v18l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5-2 1.5z"/><path d="M9 8h6M9 12h6M9 16h4"/></symbol>
<symbol id="ic-calendar" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/><path d="M8 3v4M16 3v4"/></symbol>
<symbol id="ic-bank" viewBox="0 0 24 24"><path d="M3 10 12 4l9 6"/><path d="M4 10h16v9H4z"/><path d="M4 19h16"/><path d="M7 13v4M12 13v4M17 13v4"/></symbol>
<symbol id="ic-heart" viewBox="0 0 24 24"><path d="M12 21c-4-2.4-9-6-9-11a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 5-5 8.6-9 11z"/></symbol>
<symbol id="ic-phone" viewBox="0 0 24 24"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/></symbol>
<symbol id="ic-shield" viewBox="0 0 24 24"><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/></symbol>
<symbol id="ic-dome" viewBox="0 0 24 24"><path d="M4 20h16"/><path d="M6 20v-6a6 6 0 0 1 12 0v6"/><path d="M12 8V4"/><path d="M10 4h4"/></symbol>
<symbol id="ic-run" viewBox="0 0 24 24"><circle cx="14" cy="4.5" r="1.7"/><path d="M9 20l3-5 2 2 3 3"/><path d="M6 13l4-3 2 2 4-1"/></symbol>
<symbol id="ic-store" viewBox="0 0 24 24"><path d="M4 9 5 4h14l1 5"/><path d="M4 9h16v11H4z"/><path d="M10 20v-5h4v5"/></symbol>
<symbol id="ic-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/></symbol>
<symbol id="ic-file-check" viewBox="0 0 24 24"><path d="M7 2h7l4 4v16H7z"/><path d="M14 2v4h4"/><path d="M9.5 14l2 2 4-4"/></symbol>
<symbol id="ic-gift" viewBox="0 0 24 24"><rect x="3" y="9" width="18" height="12" rx="1"/><path d="M3 13h18"/><path d="M12 9v12"/><path d="M12 9C9 9 8 7 8 6a2 2 0 0 1 4 0 2 2 0 0 1 4 0c0 1-1 3-4 3z"/></symbol>
<symbol id="ic-moon" viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/></symbol>
<symbol id="ic-bar-chart" viewBox="0 0 24 24"><path d="M4 20V10M11 20V4M18 20v-7"/><path d="M2 20h20"/></symbol>
<symbol id="ic-cross" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M12 8v8M8 12h8"/></symbol>
<symbol id="ic-droplet" viewBox="0 0 24 24"><path d="M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11z"/></symbol>
<symbol id="ic-palm" viewBox="0 0 24 24"><path d="M12 22V10"/><path d="M12 10C9 8 6 8 4 6c2-2 6-2 8 2"/><path d="M12 10c3-2 6-2 8-4-2-2-6-2-8 2"/></symbol>
<symbol id="ic-backpack" viewBox="0 0 24 24"><path d="M8 4h8v3H8z"/><path d="M6 8h12v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1z"/><path d="M9 12h6M9 16h6"/></symbol>
<symbol id="ic-exchange" viewBox="0 0 24 24"><path d="M4 8h13"/><path d="M13 4l4 4-4 4"/><path d="M20 16H7"/><path d="M11 20l-4-4 4-4"/></symbol>
<symbol id="ic-baby" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M6 20c0-4 3-6 6-6s6 2 6 6"/><path d="M10 8h.01M14 8h.01"/></symbol>
<symbol id="ic-grad-cap" viewBox="0 0 24 24"><path d="M12 4 2 9l10 5 10-5z"/><path d="M6 12v5c0 1.5 3 3 6 3s6-1.5 6-3v-5"/></symbol>
<symbol id="ic-bolt" viewBox="0 0 24 24"><path d="M13 2 4 14h6l-1 8 9-12h-6z"/></symbol>
<symbol id="ic-calculator" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 6h8"/><path d="M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 19h.01M12 19h.01"/></symbol>
</svg>
"""


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


def rss_feed(cfg, domain, articles, build_day) -> str:
    """Feed RSS untuk /panduan/ (membantu penemuan & pengindeksan artikel)."""
    def rfc822(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime(
                "%a, %d %b %Y 00:00:00 +0000")
        except (ValueError, TypeError):
            return ""
    esc = html.escape
    items = []
    for a in sorted(articles,
                    key=lambda x: x.get("updated") or x.get("date", ""),
                    reverse=True)[:20]:
        url = f'{domain}/panduan/{a["slug"]}/'
        pub = rfc822(a.get("updated") or a.get("date"))
        items.append(
            "<item>"
            f"<title>{esc(a['title'])}</title>"
            f"<link>{url}</link>"
            f'<guid isPermaLink="true">{url}</guid>'
            + (f"<pubDate>{pub}</pubDate>" if pub else "")
            + f"<description>{esc(a['description'])}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f'<title>{esc(cfg["site_name"])} - Panduan</title>'
        f'<link>{domain}/panduan/</link>'
        f'<description>{esc(cfg["tagline"])}</description>'
        "<language>id-ID</language>"
        f"<lastBuildDate>{rfc822(build_day)}</lastBuildDate>"
        + "".join(items) +
        "</channel></rss>"
    )


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
        "CATNAV": catnav_html(cfg),
        "ICON_SPRITE": ICON_SPRITE,
        "JSONLD": "",
        "BREADCRUMB": "",
        "RELATED": "",
        "FEEDBACK": "",
        "BODYCLASS": "",
        "OG_TYPE": "website",
        "OG_IMAGE": f"{domain}/assets/og.png",
        "META_ROBOTS": "index, follow, max-image-preview:large, "
                       "max-snippet:-1, max-video-preview:-1",
        "HEAD_EXTRA": "",
    }
    urls = [f"{domain}/", f"{domain}/alat/"]
    url_lastmod = {}

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
            "JSONLD": (
                jsonld_page(cfg, p, inner, domain) if is_calc
                else jsonld_about(cfg, domain) if slug == "tentang"
                else ""),
            "BREADCRUMB": breadcrumb_html(p) if is_calc else "",
            "RELATED": related_html(cfg, p) if is_calc else "",
            "FEEDBACK": feedback if is_calc else "",
        }
        write(DIST / slug / "index.html", render(layout, ctx))
        urls.append(f"{domain}/{slug}/")

    # --- Beranda: hero + pencarian + kartu per kategori ---
    index_pages = [p for p in cfg["pages"] if p.get("in_index")]
    by_slug = {p["slug"]: p for p in cfg["pages"]}
    popular = [by_slug[s] for s in cfg.get("primary_nav", []) if s in by_slug]
    popular_html = ""
    if popular:
        links = "\n".join(
            f'<a class="hero-pop" href="/{p["slug"]}/">'
            f'{icon_html(p.get("icon", ""), 16)}<span>{p["nav"] or p["title"]}</span></a>'
            for p in popular
        )
        popular_html = f'<div class="hero-popular">{links}</div>'
    sections = category_sections(cfg) + "\n" + coming_soon_section(cfg)
    index_inner = (
        '<div class="hero">'
        f'<h1>{cfg["site_name"]}</h1>'
        f'<p class="lead">{cfg["tagline"]}</p>'
        '<input type="search" id="cari" class="search" autocomplete="off" '
        'placeholder="Cari kalkulator… (mis. KPR, BMI, umur)">'
        f'<p class="hero-trust">{len(index_pages)} kalkulator gratis &middot; tanpa daftar '
        '&middot; data diperbarui berkala</p>'
        f'{popular_html}'
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
        "JSONLD": jsonld_tag(jsonld_itemlist(cfg, domain)),
        "ADSENSE_SLOT": "",
        "BODYCLASS": "page-wide",
    }))

    # --- 404 ---
    write(DIST / "404.html", render(layout, {
        **base_ctx,
        "TITLE": f'Halaman tidak ditemukan - {cfg["site_name"]}',
        "DESCRIPTION": "Halaman yang kamu cari tidak ada.",
        "CANONICAL": f"{domain}/404",
        "META_ROBOTS": "noindex, follow",
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
        a_url = f'{domain}/panduan/{a["slug"]}/'
        pub_dt = a.get("date") or ""
        mod_dt = a.get("updated") or a.get("date") or ""
        head_extra = (
            f'<meta property="article:published_time" content="{pub_dt}">'
            f'<meta property="article:modified_time" content="{mod_dt}">'
            '<meta property="article:section" content="Panduan">'
            f'<meta name="author" content="{cfg.get("publisher", {}).get("name", cfg["site_name"])}">'
        )
        write(DIST / "panduan" / a["slug"] / "index.html", render(layout, {
            **base_ctx,
            "TITLE": f'{a["title"]} - {cfg["site_name"]}',
            "DESCRIPTION": a["description"],
            "CANONICAL": a_url,
            "CONTENT": art_inner,
            "JSONLD": jsonld_article(a, body, domain, cfg["site_name"], cfg),
            "FEEDBACK": feedback,
            "ADSENSE_SLOT": "",
            "OG_TYPE": "article",
            "HEAD_EXTRA": head_extra,
        }))
        urls.append(a_url)
        url_lastmod[a_url] = mod_dt or today

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

    # --- sitemap.xml + robots.txt + feed.xml ---
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"  <url><loc>{u}</loc><lastmod>{url_lastmod.get(u, today)}</lastmod></url>"
           for u in urls]
    sm.append("</urlset>")
    write(DIST / "sitemap.xml", "\n".join(sm))
    write(DIST / "robots.txt",
          f"User-agent: *\nAllow: /\n\nSitemap: {domain}/sitemap.xml\n")
    if articles:
        write(DIST / "feed.xml", rss_feed(cfg, domain, articles, today))

    # --- ads.txt (Google AdSense) ---
    ads_client = cfg.get("adsense_client", "").strip()
    if ads_client:
        pub = ads_client.replace("ca-", "", 1)
        write(DIST / "ads.txt",
              f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")

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
