/* Bật/tắt thông báo cảnh báo AQI chạy nền (Web Push). Tự vẽ vào phần tử #khuDay nếu trang có.
   Cần: HTTPS (hoặc localhost), trình duyệt hỗ trợ Push API, service worker sw.js đã đăng ký (pwa.js).
   iPhone/iPad: chỉ hoạt động khi web được "Thêm vào màn hình chính" (iOS 16.4+).
   App Android AirHCM dùng tác vụ nền riêng (mobile/runners/kiem_tra_aqi.js) vì WebView không hỗ trợ Web Push. */
(function () {
  var khu = document.getElementById('khuDay');
  if (!khu) return;
  var API = (window.API_ORIGIN || '') + '/api/v1/day';
  var MUC = [[101, 'Kém trở lên (AQI ≥ 101)'], [151, 'Xấu trở lên (AQI ≥ 151)'], [201, 'Rất xấu trở lên (AQI ≥ 201)'], [51, 'Trung bình trở lên (AQI ≥ 51)']];

  function tb(text, loai) {
    var c = document.getElementById('tbDay'); if (!c) return;
    var d = document.createElement('div'); d.className = 'tb ' + loai; d.textContent = text; c.textContent = ''; c.appendChild(d);
  }
  function b64(s) {
    var p = '='.repeat((4 - s.length % 4) % 4), r = atob((s + p).replace(/-/g, '+').replace(/_/g, '/'));
    var a = new Uint8Array(r.length); for (var i = 0; i < r.length; i++) a[i] = r.charCodeAt(i); return a;
  }
  function post(duong, body) {
    return fetch(API + duong, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.detail || 'Lỗi ' + r.status); return d; }); });
  }

  if (/AirHCM-App/.test(navigator.userAgent)) {
    khu.innerHTML = '<div class="tb info">Bạn đang dùng app Android: app tự kiểm tra AQI mỗi 30 phút và báo khi vượt mức "Kém", kể cả khi đã đóng app. Có thể chỉnh trong Cài đặt → Ứng dụng → AirHCM → Thông báo.</div>';
    return;
  }
  var hoTro = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  if (!hoTro || !window.isSecureContext) {
    var ios = /iPhone|iPad/.test(navigator.userAgent);
    khu.innerHTML = '<div class="tb info">' + (!window.isSecureContext ? 'Thông báo nền cần kết nối HTTPS (bản triển khai trên Internet).' :
      ios ? 'Trên iPhone/iPad: bấm nút Chia sẻ → "Thêm vào MH chính", mở AirHCM từ màn hình chính rồi bật tại đây.' :
      'Trình duyệt này chưa hỗ trợ thông báo nền. Hãy dùng Chrome, Edge hoặc Firefox bản mới.') + '</div>';
    return;
  }

  var sel = document.createElement('select');
  MUC.forEach(function (m) { var o = document.createElement('option'); o.value = m[0]; o.textContent = m[1]; sel.appendChild(o); });
  sel.style.cssText = 'padding:9px 10px;border-radius:10px;border:1.5px solid var(--border);font:inherit';
  var nhan = document.createElement('label'); nhan.className = 'chuyen';
  var hop = document.createElement('input'); hop.type = 'checkbox';
  var chu = document.createElement('span'); chu.textContent = 'Nhận thông báo nền trên thiết bị này';
  nhan.appendChild(hop); nhan.appendChild(chu);
  var nutThu = document.createElement('button'); nutThu.className = 'nut phu'; nutThu.textContent = 'Gửi thông báo thử'; nutThu.disabled = true;
  var hang = document.createElement('div'); hang.className = 'hang-nut'; hang.style.alignItems = 'center';
  hang.appendChild(sel); hang.appendChild(nutThu);
  var o = document.createElement('div'); o.className = 'o-nhap';
  var tbEl = document.createElement('div'); tbEl.id = 'tbDay';
  o.appendChild(nhan); o.appendChild(hang); o.appendChild(tbEl); khu.appendChild(o);

  var dk = null;
  function capNhat() { hop.checked = !!dk; nutThu.disabled = !dk; }

  navigator.serviceWorker.ready.then(function (reg) {
    return reg.pushManager.getSubscription().then(function (s) {
      dk = s; capNhat();
      if (s) post('/trang-thai', { endpoint: s.endpoint }).then(function (d) {
        if (d.dang_ky) sel.value = d.dang_ky.nguong_aqi; else { dk = null; capNhat(); }   // máy chủ đã xóa (vd. lỗi lâu ngày)
      }).catch(function () {});
    });
  });

  function batDay() {
    return Notification.requestPermission().then(function (q) {
      if (q !== 'granted') throw new Error('Bạn chưa cho phép thông báo. Mở cài đặt trang web của trình duyệt để cho phép.');
      return Promise.all([navigator.serviceWorker.ready, fetch(API + '/khoa-cong-khai').then(function (r) { return r.json(); })]);
    }).then(function (x) {
      return x[0].pushManager.getSubscription().then(function (s) {
        return s || x[0].pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(x[1].khoa) });
      });
    }).then(function (s) {
      dk = s;
      return post('/dang-ky', { dang_ky: s.toJSON(), nguong: +sel.value });
    });
  }

  hop.onchange = function () {
    hop.disabled = true;
    var viec = hop.checked ? batDay().then(function (d) { tb(d.message, 'ok'); })
      : (dk ? post('/huy', { endpoint: dk.endpoint }).catch(function () {}).then(function () { return dk.unsubscribe(); }) : Promise.resolve())
          .then(function () { dk = null; tb('Đã tắt thông báo nền trên thiết bị này', 'info'); });
    viec.catch(function (e) { tb(e.message, 'loi'); dk = dk && hop.checked ? dk : null; })
      .then(function () { hop.disabled = false; capNhat(); });
  };
  sel.onchange = function () { if (dk) post('/dang-ky', { dang_ky: dk.toJSON(), nguong: +sel.value }).then(function (d) { tb(d.message, 'ok'); }, function (e) { tb(e.message, 'loi'); }); };
  nutThu.onclick = function () {
    if (!dk) return;
    nutThu.disabled = true;
    post('/thu', { endpoint: dk.endpoint }).then(function (d) { tb(d.message + ' – kiểm tra khay thông báo của hệ điều hành.', 'ok'); }, function (e) { tb(e.message, 'loi'); })
      .then(function () { nutThu.disabled = false; });
  };
})();
