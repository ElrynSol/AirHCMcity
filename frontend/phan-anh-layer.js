/* Lớp "Phản ánh của người dân" trên bản đồ (trang Bản đồ và trang Phản ánh ô nhiễm): đọc /api/v1/phan-anh,
   vẽ điểm tròn có biểu tượng theo loại. Viền đứt = chưa xác minh, viền cam liền = quản trị viên đã xác minh.
   Bấm vào điểm để xem và bấm "Tôi cũng thấy". Cần biến toàn cục `map` (Leaflet). */
(function () {
  if (typeof map === 'undefined' || !window.L) return;
  var API = (window.API_ORIGIN || '') + '/api/v1';
  var lop = L.layerGroup().addTo(map), nghe = [];

  var css = document.createElement('style');
  css.textContent =
    '.pa-dau{width:32px;height:32px;border-radius:50%;background:#fff;border:2.5px dashed #98a2b3;box-shadow:0 2px 8px rgba(0,0,0,.35);' +
    'display:flex;align-items:center;justify-content:center;font-size:16px;line-height:1}' +
    '.pa-dau.xm{border:3px solid #f97316}' +
    '.pa-dau i{position:absolute;top:-6px;right:-8px;min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:#1b63d6;color:#fff;' +
    'font:700 10.5px/17px var(--font,sans-serif);font-style:normal;text-align:center}' +
    '.pa-pop{font-size:13px;line-height:1.5;min-width:190px}.pa-pop .tag{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:8px}' +
    '.pa-pop .tag.moi{background:#eef2f6;color:#475467}.pa-pop .tag.xm{background:#ffedd5;color:#c2410c}' +
    '.pa-pop button{margin-top:6px;padding:6px 10px;border:0;border-radius:8px;background:#1b63d6;color:#fff;font:600 12.5px var(--font,sans-serif);cursor:pointer}' +
    '.pa-pop button:disabled{background:#98a2b3;cursor:default}';
  document.head.appendChild(css);

  var esc = function (x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  function truoc(iso) {
    var p = Math.max(0, (Date.now() - new Date(iso).getTime()) / 60000);
    return p < 1 ? 'vừa xong' : p < 60 ? Math.round(p) + ' phút trước' : p < 1440 ? Math.round(p / 60) + ' giờ trước' : Math.round(p / 1440) + ' ngày trước';
  }
  function nd(p) {
    var xm = p.trang_thai === 'xac_minh';
    return '<div class="pa-pop"><b>' + esc(p.bieu_tuong) + ' ' + esc(p.ten_loai) + '</b><br>' +
      '<span class="tag ' + (xm ? 'xm">ĐÃ XÁC MINH' : 'moi">CHƯA XÁC MINH') + '</span> · ' + truoc(p.tao_luc) + '<br>' +
      (p.phuong ? '<small>📍 ' + esc(p.phuong) + '</small><br>' : '') +
      (p.mo_ta ? '<span>' + esc(p.mo_ta) + '</span><br>' : '') +
      (p.aqi_tp != null ? '<small>AQI thành phố lúc gửi: ' + esc(p.aqi_tp) + '</small><br>' : '') +
      '<small>👥 ' + p.so_xac_nhan + ' người khác cũng thấy</small><br>' +
      (p.cua_toi ? '<small>Phản ánh của bạn</small>' :
        '<button type="button" data-pa-xn="' + p.id + '"' + (p.da_xac_nhan ? ' disabled>Bạn đã xác nhận' : '>👍 Tôi cũng thấy') + '</button>') +
      (/phan-anh\.html$/.test(location.pathname) ? '' : '<br><a href="phan-anh.html">Gửi phản ánh →</a>') + '</div>';
  }

  function ve(ds) {
    lop.clearLayers();
    ds.forEach(function (p) {
      var html = '<div class="pa-dau' + (p.trang_thai === 'xac_minh' ? ' xm' : '') + '" style="position:relative">' + esc(p.bieu_tuong) +
        (p.so_xac_nhan ? '<i>' + p.so_xac_nhan + '</i>' : '') + '</div>';
      L.marker([p.vi_do, p.kinh_do], { icon: L.divIcon({ className: '', html: html, iconSize: [32, 32], iconAnchor: [16, 16] }),
        zIndexOffset: 800, title: 'Phản ánh: ' + p.ten_loai }).addTo(lop).bindPopup(nd(p));
    });
  }

  function tai() {
    return fetch(API + '/phan-anh', { credentials: 'include', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : { phan_anh: [] }; })
      .then(function (d) { ve(d.phan_anh || []); nghe.forEach(function (f) { try { f(d); } catch (e) {} }); return d; })
      .catch(function () {});
  }

  // Nút "Tôi cũng thấy" trong khung thông tin của điểm
  map.getContainer().addEventListener('click', function (e) {
    var nut = e.target.closest && e.target.closest('[data-pa-xn]');
    if (!nut || nut.disabled) return;
    nut.disabled = true;
    fetch(API + '/phan-anh/' + nut.getAttribute('data-pa-xn') + '/xac-nhan', { method: 'POST', credentials: 'include' })
      .then(function (r) {
        if (r.status === 401) { location.href = 'login.html?tiep=' + encodeURIComponent(location.pathname.split('/').pop() || 'index.html'); return null; }
        return r.json().then(function (d) { nut.textContent = r.ok ? 'Đã ghi nhận 👍' : (d.detail || 'Không thực hiện được'); if (r.ok) setTimeout(tai, 800); });
      }).catch(function () { nut.disabled = false; });
  }, true);   // pha capture: Leaflet chặn sự kiện click lan ra khỏi khung popup nên phải bắt trước khi tới popup

  // Công tắc bật/tắt lớp trong bảng "Lớp bản đồ" của trang Bản đồ
  var bang = document.getElementById('layerPanel'), nutNhiet = document.getElementById('toggleHeatmap');
  if (bang && nutNhiet) {
    var nhan = document.createElement('label'); nhan.className = 'toggle-row'; nhan.title = 'Khói, đốt rác, bụi công trình... do người dân gửi trong 72 giờ qua';
    var o = document.createElement('input'); o.type = 'checkbox'; o.checked = true;
    o.onchange = function () { if (o.checked) lop.addTo(map); else map.removeLayer(lop); };
    nhan.appendChild(o); nhan.appendChild(document.createTextNode(' 📣 Phản ánh của người dân'));
    bang.insertBefore(nhan, nutNhiet);
  }

  window.PhanAnhLayer = { tai: tai, khiCoDuLieu: function (f) { nghe.push(f); } };
  tai();
  setInterval(function () { if (!document.hidden) tai(); }, 60000);
})();
