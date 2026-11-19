/* Thang VN_AQI dùng chung cho mọi trang (QĐ 1459/QĐ-TCMT ngày 12/11/2019).
   Ý nghĩa = Bảng 4, khuyến nghị = Bảng 5 của QĐ (nguyên văn; sửa lỗi chính tả "Cảnh báo hưởng" → "Cảnh báo ảnh hưởng").
   Phải khớp với ml/tinh_aqi.py (THANG_AQI); API /api/v1/aqi/thang-do trả cùng nội dung.
   Dùng:  AQI_VN.mau(aqi) · AQI_VN.ten(aqi) · AQI_VN.muc(aqi) · AQI_VN.theoTen('Kém') · AQI_VN.chuThich(el) */
(function () {
  var THANG = [
    { tu: 0, den: 50, ten: 'Tốt', lop: 'tot', mau: '#00e400', chu: '#000', dam: '#007a00', bieuTuong: '',
      yNghia: 'Chất lượng không khí tốt, không ảnh hưởng tới sức khỏe.',
      binhThuong: 'Tự do thực hiện các hoạt động ngoài trời.',
      nhayCam: 'Tự do thực hiện các hoạt động ngoài trời.' },
    { tu: 51, den: 100, ten: 'Trung bình', lop: 'trung-binh', mau: '#ffff00', chu: '#000', dam: '#8a6d00', bieuTuong: '',
      yNghia: 'Chất lượng không khí ở mức chấp nhận được. Tuy nhiên, đối với những người nhạy cảm (người già, trẻ em, người mắc các bệnh hô hấp, tim mạch…) có thể chịu những tác động nhất định tới sức khỏe.',
      binhThuong: 'Tự do thực hiện các hoạt động ngoài trời.',
      nhayCam: 'Nên theo dõi các triệu chứng như ho hoặc khó thở, nhưng vẫn có thể hoạt động bên ngoài.' },
    { tu: 101, den: 150, ten: 'Kém', lop: 'kem', mau: '#ff7e00', chu: '#000', dam: '#b45309', bieuTuong: '',
      yNghia: 'Những người nhạy cảm gặp phải các vấn đề về sức khỏe, những người bình thường ít ảnh hưởng.',
      binhThuong: 'Những người thấy có triệu chứng đau mắt, ho hoặc đau họng… nên cân nhắc giảm các hoạt động ngoài trời. Đối với học sinh, có thể hoạt động bên ngoài, nhưng nên giảm bớt việc tập thể dục kéo dài.',
      nhayCam: 'Nên giảm các hoạt động mạnh và giảm thời gian hoạt động ngoài trời. Những người mắc bệnh hen suyễn có thể cần sử dụng thuốc thường xuyên hơn.' },
    { tu: 151, den: 200, ten: 'Xấu', lop: 'xau', mau: '#ff0000', chu: '#fff', dam: '#c50000', bieuTuong: '',
      yNghia: 'Những người bình thường bắt đầu có các ảnh hưởng tới sức khỏe, nhóm người nhạy cảm có thể gặp những vấn đề sức khỏe nghiêm trọng hơn.',
      binhThuong: 'Mọi người nên giảm các hoạt động mạnh khi ở ngoài trời, tránh tập thể dục kéo dài và nghỉ ngơi nhiều hơn trong nhà.',
      nhayCam: 'Nên ở trong nhà và giảm hoạt động mạnh. Nếu cần thiết phải ra ngoài, hãy đeo khẩu trang đạt tiêu chuẩn.' },
    { tu: 201, den: 300, ten: 'Rất xấu', lop: 'rat-xau', mau: '#8f3f97', chu: '#fff', dam: '#8f3f97', bieuTuong: '',
      yNghia: 'Cảnh báo ảnh hưởng tới sức khỏe: mọi người bị ảnh hưởng tới sức khỏe nghiêm trọng hơn.',
      binhThuong: 'Mọi người hạn chế tối đa các hoạt động ngoài trời và chuyển tất cả các hoạt động vào trong nhà. Nếu cần thiết phải ra ngoài, hãy đeo khẩu trang đạt tiêu chuẩn.',
      nhayCam: 'Nên ở trong nhà và giảm hoạt động mạnh.' },
    { tu: 301, den: 500, ten: 'Nguy hại', lop: 'nguy-hai', mau: '#7e0023', chu: '#fff', dam: '#7e0023', bieuTuong: '',
      yNghia: 'Cảnh báo khẩn cấp về sức khỏe: Toàn bộ dân số bị ảnh hưởng tới sức khỏe tới mức nghiêm trọng.',
      binhThuong: 'Mọi người nên ở trong nhà, đóng cửa ra vào và cửa sổ. Nếu cần thiết phải ra ngoài, hãy đeo khẩu trang đạt tiêu chuẩn.',
      nhayCam: 'Mọi người nên ở trong nhà, đóng cửa ra vào và cửa sổ. Nếu cần thiết phải ra ngoài, hãy đeo khẩu trang đạt tiêu chuẩn.' }
  ];
  var KHONG_RO = { ten: 'Không xác định', lop: 'khong-ro', mau: '#98a2b3', chu: '#fff', dam: '#667085', bieuTuong: '·',
                   yNghia: '', binhThuong: '', nhayCam: '' };

  function muc(aqi) {
    if (aqi == null || aqi === '' || !isFinite(aqi)) return KHONG_RO;
    aqi = Math.round(Number(aqi));
    for (var i = 0; i < THANG.length; i++) if (aqi <= THANG[i].den) return THANG[i];
    return THANG[THANG.length - 1];
  }
  function theoTen(ten) {
    for (var i = 0; i < THANG.length; i++) if (THANG[i].ten === ten) return THANG[i];
    return KHONG_RO;
  }

  /* Chú thích thang màu chuẩn (6 ô). opts.gon = true: chỉ dải màu + mốc số. */
  function chuThich(el, opts) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (!el) return;
    opts = opts || {};
    el.classList.add('aqi-chu-thich');
    el.setAttribute('role', 'list');
    el.setAttribute('aria-label', 'Thang chỉ số chất lượng không khí VN_AQI');
    el.innerHTML = THANG.map(function (m) {
      return '<div class="aqi-o" role="listitem" style="background:' + m.mau + ';color:' + m.chu + '" title="' + m.yNghia + '">' +
        (opts.gon ? '' : '<span class="aqi-o-bt" aria-hidden="true">' + m.bieuTuong + '</span>') +
        '<span class="aqi-o-so">' + m.tu + '–' + m.den + '</span><span class="aqi-o-ten">' + m.ten + '</span></div>';
    }).join('') + (opts.gon ? '' : '<div class="aqi-nguon">Theo QĐ 1459/QĐ-TCMT (VN_AQI)</div>');
  }

  /* Huy hiệu mức AQI dạng HTML: "<span class=aqi-huy-hieu>87 · Trung bình</span>" */
  function huyHieu(aqi, chiTen) {
    var m = muc(aqi);
    return '<span class="aqi-huy-hieu" style="background:' + m.mau + ';color:' + m.chu + '">' +
      (chiTen ? '' : (aqi == null ? '--' : Math.round(aqi)) + ' · ') + m.ten + '</span>';
  }

  /* AQI thành phần từ nồng độ PM2.5 TB 24h (µg/m³), bảng QĐ 1459 — khớp ml/tinh_aqi.py */
  var BP_PM25 = [0, 25, 50, 80, 150, 250, 350, 500], I_AQI = [0, 50, 100, 150, 200, 300, 400, 500];
  function aqiTuPM25(c) {
    if (c == null || !isFinite(c) || c < 0) return null;
    for (var i = 0; i < BP_PM25.length - 1; i++)
      if (c <= BP_PM25[i + 1]) return Math.round((I_AQI[i + 1] - I_AQI[i]) / (BP_PM25[i + 1] - BP_PM25[i]) * (c - BP_PM25[i]) + I_AQI[i]);
    return 500;
  }

  /* Gradient cho leaflet.heat theo AQI 0..maxAqi (mặc định 300). */
  function gradientNhiet(maxAqi) {
    maxAqi = maxAqi || 300;
    var g = {};
    THANG.forEach(function (m) { var k = Math.min(1, m.den / maxAqi); if (!(k in g)) g[k] = m.mau; });
    return g;
  }

  /* ---- Đồng hồ AQI (SVG): 6 cung bằng nhau cho 6 mức, điểm đánh dấu chạy tới giá trị ----
     AQI_VN.dongHo(phầnTử | id, aqi, { toi: nền tối?, moc: hiện mốc số?, nhan: chữ dưới số (mặc định 'AQI') }) */
  var MOC = [0, 50, 100, 150, 200, 300, 500];
  var giamChuyenDong = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function gocCuaAqi(aqi) {          // 0° = đầu trái (AQI 0), 180° = đầu phải (AQI 500)
    var a = Math.max(0, Math.min(500, Number(aqi)));
    for (var i = 0; i < 6; i++)
      if (a <= MOC[i + 1]) return (i + (a - MOC[i]) / (MOC[i + 1] - MOC[i])) * 30;
    return 180;
  }
  function diem(cx, cy, r, gocTrai) {  // gocTrai: độ, tính từ đầu trái theo chiều kim đồng hồ
    var t = (180 - gocTrai) * Math.PI / 180;
    return [cx + r * Math.cos(t), cy - r * Math.sin(t)];
  }
  function demSo(el, toi, ms) {
    if (giamChuyenDong || !window.requestAnimationFrame) { el.textContent = toi; return; }
    var t0 = null;
    function buoc(t) {
      if (t0 === null) t0 = t;
      var k = Math.min(1, (t - t0) / ms);
      el.textContent = Math.round(toi * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(buoc);
    }
    requestAnimationFrame(buoc);
  }
  function dongHo(el, aqi, opts) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (!el) return;
    opts = opts || {};
    var cx = 120, cy = 126, r = 96, w = 16, cung = '', moc = '';
    for (var i = 0; i < 6; i++) {
      var a = diem(cx, cy, r, i * 30 + (i ? 1.2 : 0)), b = diem(cx, cy, r, (i + 1) * 30 - (i < 5 ? 1.2 : 0));
      cung += '<path d="M' + a[0].toFixed(1) + ' ' + a[1].toFixed(1) + ' A' + r + ' ' + r + ' 0 0 1 ' + b[0].toFixed(1) + ' ' + b[1].toFixed(1) +
        '" stroke="' + THANG[i].mau + '" stroke-width="' + w + '" fill="none" stroke-linecap="' + (i === 0 || i === 5 ? 'round' : 'butt') + '"/>';
    }
    if (opts.moc !== false) MOC.forEach(function (v, j) {
      var dau = j === 0 || j === 6, p = dau ? diem(cx, cy, r, j * 30) : diem(cx, cy, r + 19, j * 30);
      moc += '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] + (dau ? 22 : 3.5)).toFixed(1) + '" text-anchor="middle" font-size="9.5" fill="' + (opts.toi ? 'rgba(255,255,255,.65)' : '#98a2b3') + '">' + v + '</text>';
    });
    var co = aqi != null && isFinite(aqi), m = muc(co ? aqi : null), dau = diem(cx, cy, r, 0);
    var mauSo = opts.toi ? '#fff' : '#101828';
    el.innerHTML = '<svg class="dong-ho-aqi" viewBox="0 0 240 150" role="img" aria-label="AQI ' + (co ? Math.round(aqi) + ', ' + m.ten : 'không có dữ liệu') + '">' +
      '<path d="M' + diem(cx, cy, r, 0).join(' ') + ' A' + r + ' ' + r + ' 0 0 1 ' + diem(cx, cy, r, 180).join(' ') + '" stroke="' + (opts.toi ? 'rgba(255,255,255,.12)' : '#eef1f5') + '" stroke-width="' + (w + 6) + '" fill="none" stroke-linecap="round"/>' +
      cung + moc +
      (co ? '<g class="dh-kim" style="transform-origin:' + cx + 'px ' + cy + 'px;transform:rotate(0deg)"><circle cx="' + dau[0] + '" cy="' + dau[1] + '" r="11" fill="#fff" stroke="' + m.mau + '" stroke-width="5" filter="drop-shadow(0 1px 2px rgba(0,0,0,.35))"/></g>' : '') +
      '<text class="dh-so" x="' + cx + '" y="' + (cy - 14) + '" text-anchor="middle" font-size="46" font-weight="800" fill="' + mauSo + '" style="font-variant-numeric:tabular-nums">' + (co ? 0 : '--') + '</text>' +
      '<text x="' + cx + '" y="' + (cy + 8) + '" text-anchor="middle" font-size="12" font-weight="600" letter-spacing="1.5" fill="' + (opts.toi ? 'rgba(255,255,255,.7)' : '#667085') + '">' + (opts.nhan || 'AQI') + '</text>' +
      '</svg>';
    if (!co) return el.firstChild;
    var kim = el.querySelector('.dh-kim'), so = el.querySelector('.dh-so');
    var dich = 'rotate(' + gocCuaAqi(aqi).toFixed(1) + 'deg)';
    if (giamChuyenDong) kim.style.transform = dich;
    else { kim.style.transition = 'transform 1s cubic-bezier(.2,.8,.2,1)'; requestAnimationFrame(function () { requestAnimationFrame(function () { kim.style.transform = dich; }); }); }
    demSo(so, Math.round(aqi), 900);
    return el.firstChild;
  }

  /* Ngưỡng PM2.5 TB 24 giờ — phải khớp backend/core/nguong.py.
     QCVN 05:2023/BTNMT: 50 µg/Nm³ đến 31/12/2025, 45 µg/Nm³ từ 01/01/2026. WHO 2021 (khuyến nghị): 15 µg/m³. */
  function qcvnPM25(ngay) {
    var d = ngay ? String(ngay).slice(0, 10) : new Date().toISOString().slice(0, 10);
    return d >= '2026-01-01' ? 45 : 50;
  }

  window.AQI_VN = {
    THANG: THANG, KHONG_RO: KHONG_RO, CAN_CU: 'QĐ 1459/QĐ-TCMT',
    qcvnPM25: qcvnPM25, WHO_PM25: 15,
    muc: muc, theoTen: theoTen,
    mau: function (aqi) { return muc(aqi).mau; },
    mauChu: function (aqi) { return muc(aqi).chu; },
    mauDam: function (aqi) { return muc(aqi).dam; },
    ten: function (aqi) { return aqi == null ? '' : muc(aqi).ten; },
    aqiTuPM25: aqiTuPM25, chuThich: chuThich, huyHieu: huyHieu, gradientNhiet: gradientNhiet,
    dongHo: dongHo, demSo: demSo
  };
})();
