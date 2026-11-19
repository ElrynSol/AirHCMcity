/* Trợ lý AirHCM (giao diện): ngăn hỏi-đáp, câu trả lời hiện dần theo luồng (fetch + ReadableStream đọc text/event-stream).
   Máy chủ: POST /api/v1/tro-ly — chế độ "ai" (Gemini hoặc Claude, có khóa API) hoặc "tu_dong" (trả lời theo dữ liệu, không cần khóa).
   nav.js tạo bong bóng nổi ".tl-bong-noi" ở góc dưới phải và nạp file này khi người dùng bấm lần đầu;
   khung chat bung ra phía trên bong bóng (điện thoại: tấm trượt từ dưới lên). */
(function () {
  if (window.TroLy) return;
  var API = (window.API_ORIGIN || '') + '/api/v1';
  var KHOA = 'airhcm_tro_ly';
  var lichSu = [], dangHoi = false, khung = null, cheDo = null, model = null, ncc = null, goiY = [];
  var TEN_NCC = { gemini: 'Gemini (Google)', claude: 'Claude (Anthropic)' }, CTY = { gemini: 'Google', claude: 'Anthropic' };
  try { lichSu = JSON.parse(sessionStorage.getItem(KHOA) || '[]') || []; } catch (e) { lichSu = []; }

  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  /* Markdown tối giản và an toàn: thoát HTML trước, rồi **đậm**, *nghiêng*, `mã`, "### tiêu đề",
     dòng "- " / "* " / "• " thành gạch đầu dòng, "1. " thành danh sách đánh số (kiểu Gemini hay dùng) */
  function dinhDang(t) {
    var dong = esc(t).replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').split('\n'), html = '', ds = null;
    var nghieng = function (s) { return s.replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)\*(?!\w)/g, '$1<i>$2</i>'); };
    var dongDs = function () { if (ds) { html += '</' + ds + '>'; ds = null; } };
    dong.forEach(function (d) {
      var m = /^\s*[-•*]\s+(.*)$/.exec(d), so = /^\s*\d+[.)]\s+(.*)$/.exec(d), td = /^\s*#{1,4}\s+(.*)$/.exec(d);
      var loai = m ? 'ul' : so ? 'ol' : null;
      if (loai) { if (ds !== loai) { dongDs(); html += '<' + loai + '>'; ds = loai; } html += '<li>' + nghieng((m || so)[1]) + '</li>'; return; }
      dongDs();
      if (td) html += '<p class="tl-td"><b>' + nghieng(td[1]) + '</b></p>';
      else if (d.trim()) html += '<p>' + nghieng(d) + '</p>';
    });
    dongDs();
    return html;
  }
  /* Tên gọn cho nhãn trên đầu khung: "gemini-3.5-flash-lite" → "Gemini"; tên model đầy đủ để ở chú thích khi rê chuột */
  function tenGon() { return ncc === 'gemini' ? 'Gemini' : ncc === 'claude' ? 'Claude' : 'AI'; }
  function luu() { try { sessionStorage.setItem(KHOA, JSON.stringify(lichSu.slice(-12))); } catch (e) {} }

  function taoKhung() {
    var nen = document.createElement('div'); nen.className = 'tl-nen'; nen.onclick = dong;
    khung = document.createElement('aside');
    khung.className = 'tl-khung'; khung.setAttribute('role', 'dialog'); khung.setAttribute('aria-label', 'Trợ lý AirHCM');
    khung.innerHTML =
      '<header class="tl-dau"><div><b>Trợ lý tra cứu AirHCM</b><span class="tl-che-do" id="tlCheDo">…</span></div>' +
      '<div><button type="button" class="tl-nut" id="tlXoa" title="Cuộc trò chuyện mới">↺</button><button type="button" class="tl-nut" id="tlDong" aria-label="Đóng">✕</button></div></header>' +
      '<div class="tl-tin" id="tlTin" aria-live="polite"></div>' +
      '<div class="tl-goi-y" id="tlGoiY"></div>' +
      '<form class="tl-nhap" id="tlForm"><textarea id="tlO" rows="1" maxlength="500" placeholder="Hỏi về không khí, dự báo, sức khỏe…" aria-label="Câu hỏi"></textarea>' +
      '<button type="submit" class="tl-gui" id="tlGui" aria-label="Gửi">➤</button></form>' +
      '<div class="tl-chu-thich" id="tlChuThich"></div>';
    document.body.appendChild(nen); document.body.appendChild(khung);
    khung._nen = nen;
    khung.querySelector('#tlDong').onclick = dong;
    khung.querySelector('#tlXoa').onclick = function () { lichSu = []; luu(); veTin(); };
    var o = khung.querySelector('#tlO');
    o.addEventListener('input', function () { o.style.height = 'auto'; o.style.height = Math.min(o.scrollHeight, 120) + 'px'; });
    o.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); gui(o.value); } });
    khung.querySelector('#tlForm').onsubmit = function (e) { e.preventDefault(); gui(o.value); };
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && khung.classList.contains('mo')) dong(); });
    fetch(API + '/tro-ly/trang-thai', { credentials: 'include' }).then(function (r) { return r.json(); }).then(function (d) {
      cheDo = d.che_do; model = d.model; ncc = d.nha_cung_cap; goiY = d.goi_y || []; veCheDo(); veGoiY();
    }).catch(function () { cheDo = 'tu_dong'; veCheDo(); });
    veTin();
  }
  function veCheDo(lyDo) {
    var el = khung.querySelector('#tlCheDo');
    el.textContent = cheDo === 'ai' ? 'AI · ' + tenGon() : 'Tự động';
    el.className = 'tl-che-do ' + (cheDo === 'ai' ? 'ai' : '');
    el.title = cheDo === 'ai' ? 'Câu trả lời do ' + (TEN_NCC[ncc] || 'AI') + (model ? ' (' + model + ')' : '') + ' tạo từ dữ liệu hiện tại và tài liệu của đồ án'
      : 'Trả lời theo mẫu từ dữ liệu hiện tại (chưa bật AI: thêm GEMINI_API_KEY vào .env)';
    khung.querySelector('#tlChuThich').textContent = (lyDo ? lyDo + ' ' : '') + 'Trả lời dựa trên dữ liệu mô hình CAMS và tài liệu đồ án, không thay thế tư vấn y tế' +
      (cheDo === 'ai' ? '. Câu hỏi được gửi tới ' + (CTY[ncc] || 'nhà cung cấp AI') + ' để tạo câu trả lời.' : '.');
  }
  function veGoiY() {
    var el = khung.querySelector('#tlGoiY');
    el.innerHTML = lichSu.length ? '' : goiY.map(function (g) { return '<button type="button" class="tl-chip">' + esc(g) + '</button>'; }).join('');
    el.querySelectorAll('.tl-chip').forEach(function (b) { b.onclick = function () { gui(b.textContent); }; });
  }
  function veTin() {
    var el = khung.querySelector('#tlTin');
    el.innerHTML = '<div class="tl-bong tro-ly"><p>Xin chào! Bạn có thể tra cứu nhanh về <b>chất lượng không khí TP.HCM hôm nay</b> (chỉ số AQI, khuyến nghị sức khỏe, dự báo 24 giờ tới) hoặc thông tin kỹ thuật về <b>hệ thống AirHCM</b>.</p></div>' +
      lichSu.map(function (m) { return '<div class="tl-bong ' + (m.vai === 'user' ? 'nguoi' : 'tro-ly') + '">' + (m.vai === 'user' ? '<p>' + esc(m.noi_dung) + '</p>' : dinhDang(m.noi_dung)) + '</div>'; }).join('');
    el.scrollTop = el.scrollHeight;
    if (goiY.length) veGoiY();
  }

  function gui(cauHoi) {
    cauHoi = String(cauHoi || '').trim();
    if (!cauHoi || dangHoi) return;
    dangHoi = true;
    var o = khung.querySelector('#tlO'); o.value = ''; o.style.height = 'auto';
    khung.querySelector('#tlGui').disabled = true;
    var truoc = lichSu.slice();
    lichSu.push({ vai: 'user', noi_dung: cauHoi });
    veTin();
    var hop = document.createElement('div'); hop.className = 'tl-bong tro-ly dang-go'; hop.innerHTML = '<span class="tl-cham"><i></i><i></i><i></i></span>';
    var tin = khung.querySelector('#tlTin'); tin.appendChild(hop); tin.scrollTop = tin.scrollHeight;
    var traLoi = '';

    function xong(loiMsg) {
      dangHoi = false; khung.querySelector('#tlGui').disabled = false;
      hop.classList.remove('dang-go');
      if (loiMsg && !traLoi) { hop.classList.add('loi'); hop.innerHTML = '<p>' + esc(loiMsg) + '</p>'; lichSu.pop(); }
      else { if (loiMsg) hop.insertAdjacentHTML('beforeend', '<p class="tl-loi-nho">' + esc(loiMsg) + '</p>'); lichSu.push({ vai: 'assistant', noi_dung: traLoi }); }
      luu();
      if (dangMo()) o.focus(); else if (bong()) bong().classList.add('co-tin');   // thu khung lúc đang trả lời: chấm đỏ báo có tin mới
    }
    function xuLy(suKien, d) {
      if (suKien === 'che_do') { cheDo = d.che_do; if (d.model) model = d.model; if (d.nha_cung_cap) ncc = d.nha_cung_cap; veCheDo(d.ly_do); }
      else if (suKien === 'chu') { traLoi += d.t || ''; hop.classList.remove('dang-go'); hop.innerHTML = dinhDang(traLoi); tin.scrollTop = tin.scrollHeight; }
      else if (suKien === 'xong') { if (d.che_do === 'ai' && d.model && d.model !== model) { model = d.model; veCheDo(); } }
      else if (suKien === 'loi') { hop.insertAdjacentHTML('beforeend', '<p class="tl-loi-nho">' + esc(d.thong_bao) + '</p>'); }
    }
    fetch(API + '/tro-ly', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify({ cau_hoi: cauHoi, lich_su: truoc }) })
      .then(function (r) {
        if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.detail || ('Lỗi ' + r.status)); });
        if (!r.body || !r.body.getReader) return r.text().then(function (t) { phanTich(t, xuLy); xong(); });
        var doc = r.body.getReader(), giai = new TextDecoder(), dem = '';
        return (function doc1() {
          return doc.read().then(function (k) {
            if (k.done) { if (dem.trim()) phanTich(dem, xuLy); xong(); return; }
            dem += giai.decode(k.value, { stream: true });
            var cat = dem.lastIndexOf('\n\n');
            if (cat >= 0) { phanTich(dem.slice(0, cat), xuLy); dem = dem.slice(cat + 2); }
            return doc1();
          });
        })();
      })
      .catch(function (e) { xong(e.message || 'Không kết nối được máy chủ.'); });
  }
  function phanTich(van, cb) {
    van.split('\n\n').forEach(function (khoi) {
      var ev = 'message', du = [];
      khoi.split('\n').forEach(function (d) { if (d.indexOf('event: ') === 0) ev = d.slice(7); else if (d.indexOf('data: ') === 0) du.push(d.slice(6)); });
      if (!du.length) return;
      try { cb(ev, JSON.parse(du.join('\n'))); } catch (e) {}
    });
  }

  function bong() { return document.querySelector('.tl-bong-noi'); }
  function dangMo() { return !!khung && khung.classList.contains('mo'); }
  function mo(cauHoi) {
    if (!khung) taoKhung();
    khung.classList.add('mo'); khung._nen.classList.add('mo');
    document.documentElement.classList.add('tl-dang-mo');
    var b = bong(); if (b) { b.classList.add('mo'); b.classList.remove('co-tin'); b.setAttribute('aria-label', 'Thu nhỏ trợ lý'); b.setAttribute('aria-expanded', 'true'); }
    var tin = khung.querySelector('#tlTin'); tin.scrollTop = tin.scrollHeight;
    setTimeout(function () { khung.querySelector('#tlO').focus(); }, 60);
    if (cauHoi) gui(cauHoi);
  }
  function dong() {
    if (!khung) return;
    khung.classList.remove('mo'); khung._nen.classList.remove('mo');
    document.documentElement.classList.remove('tl-dang-mo');
    var b = bong(); if (b) { b.classList.remove('mo'); b.setAttribute('aria-label', 'Mở trợ lý AirHCM'); b.setAttribute('aria-expanded', 'false'); }
  }
  window.TroLy = { mo: mo, dong: dong, batTat: function () { dangMo() ? dong() : mo(); }, gui: function (q) { mo(q); } };
})();
