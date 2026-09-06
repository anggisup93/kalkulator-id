// Helper bersama untuk semua halaman kalkulator.

// Format angka jadi Rupiah: 1234567 -> "Rp 1.234.567"
function rp(n) {
  return "Rp " + Math.round(n).toLocaleString("id-ID");
}

// Ambil nilai numerik dari sebuah input.
// Toleran terhadap pemisah ribuan ("1.234.567") dan input kosong -> 0.
function num(id) {
  var el = document.getElementById(id);
  if (!el) return 0;
  var raw = String(el.value).replace(/[^\d,.-]/g, "");
  // Buang titik ribuan, ubah koma desimal jadi titik.
  raw = raw.replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".");
  return parseFloat(raw) || 0;
}

// Tampilkan hasil di elemen ber-id tertentu.
// shareText opsional: kalau diisi, tombol "Cetak / PDF" + "Bagikan" ikut muncul.
function show(id, html, shareText) {
  var el = document.getElementById(id);
  if (!el) return;
  if (shareText) html += actions(shareText);
  el.innerHTML = html;
  el.hidden = false;
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// Tombol aksi hasil: salin, cetak/simpan PDF, bagikan ke WhatsApp (+ link halaman).
function actions(shareText) {
  var link = location.origin + location.pathname;
  var wa = "https://wa.me/?text=" + encodeURIComponent(shareText + "\n" + link);
  var esc = String(shareText).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  return (
    '<div class="result-actions" data-noprint>' +
    '<button type="button" class="btn-sec" data-copy="' + esc + '" onclick="salinHasil(this)">Salin</button>' +
    '<button type="button" class="btn-sec" onclick="window.print()">Cetak / PDF</button>' +
    '<a class="btn-sec" target="_blank" rel="noopener" href="' + wa + '">Bagikan ke WhatsApp</a>' +
    "</div>"
  );
}

// Salin teks hasil ke clipboard.
function salinHasil(btn) {
  var t = btn.getAttribute("data-copy") || "";
  var done = function () {
    var old = btn.textContent;
    btn.textContent = "Tersalin ✓";
    setTimeout(function () { btn.textContent = old; }, 1500);
  };
  if (navigator.clipboard) {
    navigator.clipboard.writeText(t).then(done, done);
  } else {
    var ta = document.createElement("textarea");
    ta.value = t;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
    done();
  }
}

// Bar komposisi sederhana: potongan = [{label, nilai, warna}]
function bar(potongan) {
  var total = potongan.reduce(function (s, x) { return s + Math.max(0, x.nilai); }, 0) || 1;
  var seg = potongan.map(function (x) {
    var pct = (Math.max(0, x.nilai) / total) * 100;
    return '<span style="width:' + pct.toFixed(2) + '%;background:' + x.warna +
           '" title="' + x.label + '"></span>';
  }).join("");
  var leg = potongan.map(function (x) {
    return '<li><i style="background:' + x.warna + '"></i>' + x.label + "</li>";
  }).join("");
  return '<div class="bar">' + seg + "</div><ul class=\"bar-legend\">" + leg + "</ul>";
}

// Format input uang dengan pemisah ribuan saat diketik.
// Aktif otomatis untuk setiap <input data-money>.
(function () {
  function fmt(v) {
    var digits = String(v).replace(/\D/g, "").replace(/^0+(?=\d)/, "");
    return digits ? parseInt(digits, 10).toLocaleString("id-ID") : "";
  }
  function wire(el) {
    el.value = fmt(el.value);
    el.addEventListener("input", function () {
      var start = el.selectionStart;
      var before = el.value.length;
      el.value = fmt(el.value);
      var after = el.value.length;
      if (start != null) el.selectionStart = el.selectionEnd = start + (after - before);
    });
  }
  function init() {
    var list = document.querySelectorAll("input[data-money]");
    for (var i = 0; i < list.length; i++) wire(list[i]);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

// Label "tarif & ketentuan berlaku" pada kalkulator kebijakan (elemen [data-policy]).
(function () {
  function init() {
    var d = window.KID_DATA || {};
    var list = document.querySelectorAll("[data-policy]");
    for (var i = 0; i < list.length; i++) {
      list[i].className = "art-meta";
      list[i].textContent = "Tarif & ketentuan mengikuti aturan " + (d.tahun_berlaku || "") +
        (d.diperbarui ? " · diperbarui " + d.diperbarui : "") +
        ". Selalu verifikasi dengan sumber resmi.";
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();

// Kirim form (masukan / kontak) via AJAX ke Web3Forms tanpa pindah halaman.
function kirimForm(form, onDone) {
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = form.querySelector('button[type="submit"]');
    if (btn) { btn.disabled = true; btn.textContent = "Mengirim…"; }
    fetch(form.action, { method: "POST", body: new FormData(form) })
      .then(function (r) { return r.json(); })
      .then(function (j) { onDone(j && j.success, j); })
      .catch(function () { onDone(false); });
  });
}

// Widget masukan (jempol + form opsional).
(function () {
  function init() {
    var box = document.querySelector("[data-feedback]");
    if (!box) return;
    var key = "kid-fb:" + location.pathname;
    var form = box.querySelector(".fb-form");
    var q = box.querySelector(".fb-q");
    var buttons = box.querySelector(".fb-buttons");
    function thanks(msg) {
      if (buttons) buttons.hidden = true;
      if (form) form.hidden = true;
      q.textContent = msg;
    }
    try { if (localStorage.getItem(key)) thanks("Terima kasih, masukan Anda sudah tercatat."); } catch (e) {}

    box.querySelectorAll(".fb-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-fb");
        try { localStorage.setItem(key, v); } catch (e) {}
        if (v === "tidak" && form) {
          if (buttons) buttons.hidden = true;
          var pg = form.querySelector(".fb-page");
          if (pg) pg.value = location.href;
          form.hidden = false;
          q.textContent = "Terima kasih. Apa yang bisa diperbaiki?";
          var ta = form.querySelector("textarea");
          if (ta) ta.focus();
        } else {
          thanks(v === "ya"
            ? "Senang bisa membantu. Terima kasih!"
            : "Terima kasih. Anda juga bisa mengirim koreksi lewat halaman Kontak.");
        }
      });
    });
    if (form) {
      kirimForm(form, function (ok) {
        thanks(ok ? "Masukan terkirim. Terima kasih!"
          : "Gagal mengirim. Coba lagi atau hubungi kami lewat halaman Kontak.");
      });
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();

// Form kontak (di halaman Kontak).
(function () {
  function init() {
    var form = document.getElementById("kontak-form");
    if (!form) return;
    var msg = document.getElementById("kontak-msg");
    kirimForm(form, function (ok) {
      form.hidden = true;
      if (msg) msg.textContent = ok
        ? "Pesan terkirim. Terima kasih, kami akan menindaklanjuti."
        : "Maaf, pengiriman gagal. Silakan kirim email langsung ke alamat di atas.";
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();

// Toggle tema terang/gelap.
(function () {
  function curTheme() {
    return document.documentElement.getAttribute("data-theme") ||
      (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  function init() {
    var tt = document.getElementById("theme-toggle");
    if (!tt) return;
    tt.addEventListener("click", function () {
      var next = curTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("kid-theme", next); } catch (e) {}
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

// Overlay pencarian alat (tombol header + tombol "/" + panah + Enter).
(function () {
  function init() {
    var overlay = document.getElementById("search-overlay");
    var input = document.getElementById("search-input");
    var list = document.getElementById("search-results");
    var openBtn = document.getElementById("open-search");
    var tools = window.KID_TOOLS || [];
    if (!overlay || !input || !list || !tools.length) return;
    var active = -1, shown = [];

    function render() {
      var q = input.value.trim().toLowerCase();
      shown = q
        ? tools.filter(function (t) { return t.t.indexOf(q) > -1; }).slice(0, 12)
        : tools.slice(0, 12);
      active = shown.length ? 0 : -1;
      list.innerHTML = shown.map(function (t, i) {
        return '<li class="' + (i === active ? "active" : "") + '" data-u="' + t.u + '">' +
          '<span class="sr-ic" aria-hidden="true">' + (t.i || "") + "</span>" +
          '<span class="sr-n">' + t.n + '</span><span class="sr-c">' + t.c + "</span></li>";
      }).join("") || '<li class="sr-empty">Tidak ada alat yang cocok</li>';
    }
    function move(d) {
      if (!shown.length) return;
      active = (active + d + shown.length) % shown.length;
      [].forEach.call(list.children, function (li, i) {
        li.classList.toggle("active", i === active);
      });
      if (list.children[active]) list.children[active].scrollIntoView({ block: "nearest" });
    }
    function go() {
      if (active > -1 && shown[active]) location.href = shown[active].u;
    }
    function open() {
      overlay.hidden = false;
      document.body.style.overflow = "hidden";
      input.value = "";
      render();
      setTimeout(function () { input.focus(); }, 0);
    }
    function close() {
      overlay.hidden = true;
      document.body.style.overflow = "";
    }

    if (openBtn) openBtn.addEventListener("click", open);
    document.addEventListener("keydown", function (e) {
      var tag = (e.target.tagName || "").toLowerCase();
      var typing = tag === "input" || tag === "textarea" || tag === "select";
      if (e.key === "/" && overlay.hidden && !typing) {
        e.preventDefault(); open();
      } else if (e.key === "Escape" && !overlay.hidden) {
        close();
      }
    });
    input.addEventListener("input", render);
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") { e.preventDefault(); go(); }
    });
    list.addEventListener("click", function (e) {
      var li = e.target.closest("li[data-u]");
      if (li) location.href = li.getAttribute("data-u");
    });
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

// Ingat isian form kalkulator per halaman (localStorage).
// Nonaktif untuk <form class="calc" data-nosave> atau field ber-atribut data-nosave.
(function () {
  function key() { return "kid-form:" + location.pathname; }
  function fieldsOf(form) {
    return [].slice.call(form.querySelectorAll("input[id], select[id], textarea[id]"))
      .filter(function (el) {
        return el.type !== "submit" && el.type !== "button" && !el.hasAttribute("data-nosave");
      });
  }
  function init() {
    var forms = [].slice.call(document.querySelectorAll("form.calc"))
      .filter(function (f) { return !f.hasAttribute("data-nosave"); });
    if (!forms.length) return;
    var els = [];
    forms.forEach(function (f) { els = els.concat(fieldsOf(f)); });
    if (!els.length) return;
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(key()) || "{}") || {}; } catch (e) {}
    els.forEach(function (el) {
      var v = saved[el.id];
      if (v === undefined || v === "") return;
      if (el.type === "checkbox") el.checked = !!v;
      else el.value = v;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
    function persist() {
      var o = {};
      els.forEach(function (el) {
        o[el.id] = el.type === "checkbox" ? el.checked : el.value;
      });
      try { localStorage.setItem(key(), JSON.stringify(o)); } catch (e) {}
    }
    // Tunda penyimpanan agar penulisan localStorage tidak membebani tiap ketukan.
    var timer;
    function save() {
      clearTimeout(timer);
      timer = setTimeout(persist, 600);
    }
    forms.forEach(function (f) {
      f.addEventListener("input", save);
      f.addEventListener("change", save);
    });
    addEventListener("pagehide", persist);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") persist();
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
