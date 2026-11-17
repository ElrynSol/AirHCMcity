/* Lớp "Trạm IoT (mô phỏng)" trên trang Bản đồ: hỏi /api/v1/iot/thiet-bi mỗi 5 giây, vẽ điểm vuông có chữ "IoT"
   tô màu theo AQI chuẩn (AQI_VN), viền nhấp nháy khi trạm đang gửi dữ liệu. Không có thiết bị nào thì không vẽ gì. */
(function () {
  if (typeof map === 'undefined' || !window.L) return;
  var API = (window.API_ORIGIN || '') + '/api/v1';
  var lop = L.layerGroup().addTo(map), dau = {};

  var css = document.createElement('style');
  css.textContent =
    '.iot-dau{position:relative;width:34px;height:34px;border-radius:9px;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.45);' +
    'display:flex;align-items:center;justify-content:center;font:800 11px/1 var(--font,sans-serif);letter-spacing:.02em}' +
    '.iot-dau.song::after{content:"";position:absolute;inset:-9px;border-radius:13px;border:3px solid currentColor;opacity:.0;animation:iotSong 2s ease-out infinite}' +
    '@keyframes iotSong{0%{opacity:.75;transform:scale(.75)}100%{opacity:0;transform:scale(1.35)}}' +
    '@media (prefers-reduced-motion: reduce){.iot-dau.song::after{animation:none}}' +
    '.iot-pop b.so{font-size:20px} .iot-pop .tag{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:8px;background:#e8f0fe;color:#1557b0}';
  document.head.appendChild(css);

  var esc = function (x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  function nd(t) {
    var m = AQI_VN.muc(t.aqi), tuoi = t.tuoi_giay == null ? '--' : t.tuoi_giay < 90 ? t.tuoi_giay + ' giây trước' : Math.round(t.tuoi_giay / 60) + ' phút trước';
    var so = function (x, d) { return x == null ? '--' : Number(x).toFixed(d == null ? 1 : d); };
    return '<div class="iot-pop"><b>📡 ' + esc(t.ma) + '</b> · ' + esc(t.ten) + ' <span class="tag">MÔ PHỎNG</span><br>' +
      (t.aqi != null ? 'AQI (TB 1 phút): <b class="so" style="color:' + m.dam + '">' + t.aqi + '</b> · ' + m.ten + '<br>' : 'Chưa đủ số liệu 1 phút gần nhất<br>') +
      'PM2.5 ' + so(t.pm25) + ' · PM10 ' + so(t.pm10) + ' µg/m³<br>' +
      (t.nhiet_do != null ? so(t.nhiet_do) + ' °C · ' + so(t.do_am, 0) + '% ẩm<br>' : '') +
      '<small>' + (t.truc_tuyen ? '🟢 Đang gửi dữ liệu' : '⚪ Ngừng gửi') + ' · ' + tuoi + '</small><br>' +
      '<a href="iot.html">Xem thời gian thực →</a></div>';
  }

  function ve(ds) {
    var con = {};
    ds.forEach(function (t) {
      if (t.lat == null || t.lon == null || t.tuoi_giay == null || t.tuoi_giay > 86400) return;   // ẩn trạm im lặng quá 1 ngày
      con[t.ma] = 1;
      var m = AQI_VN.muc(t.truc_tuyen ? t.aqi : null);
      var html = '<div class="iot-dau' + (t.truc_tuyen ? ' song' : '') + '" style="background:' + m.mau + ';color:' + m.chu + '">IoT</div>';
      var icon = L.divIcon({ className: '', html: html, iconSize: [34, 34], iconAnchor: [17, 17] });
      if (!dau[t.ma]) {
        dau[t.ma] = L.marker([t.lat, t.lon], { icon: icon, zIndexOffset: 900, title: 'Trạm IoT ' + String(t.ma) }).addTo(lop).bindPopup(nd(t));
      } else {
        dau[t.ma].setIcon(icon).setLatLng([t.lat, t.lon]);
        dau[t.ma].setPopupContent(nd(t));
      }
    });
    Object.keys(dau).forEach(function (k) { if (!con[k]) { lop.removeLayer(dau[k]); delete dau[k]; } });
  }

  function tai() {
    if (document.hidden) return;
    fetch(API + '/iot/thiet-bi', { credentials: 'include' }).then(function (r) { return r.ok ? r.json() : []; }).then(ve).catch(function () {});
  }
  tai();
  setInterval(tai, 5000);
  document.addEventListener('visibilitychange', tai);
})();
