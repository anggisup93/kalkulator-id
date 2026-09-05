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

// Tombol aksi hasil: cetak/simpan PDF + bagikan ke WhatsApp (beserta link halaman).
function actions(shareText) {
  var link = location.origin + location.pathname;
  var wa = "https://wa.me/?text=" + encodeURIComponent(shareText + "\n" + link);
  return (
    '<div class="result-actions" data-noprint>' +
    '<button type="button" class="btn-sec" onclick="window.print()">Cetak / PDF</button>' +
    '<a class="btn-sec" target="_blank" rel="noopener" href="' + wa + '">Bagikan ke WhatsApp</a>' +
    "</div>"
  );
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
