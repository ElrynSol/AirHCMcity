/* Service worker: chạy offline phần giao diện, API ưu tiên mạng (có bản lưu gần nhất khi mất mạng),
   nhận thông báo đẩy (Web Push) khi AQI vượt ngưỡng — kể cả lúc đã đóng trang. */
const PHIEN_BAN = 'aqi-v6-10';  // v6.1: đăng nhập Google / Facebook / Zalo
const LOI = ['./', 'tong-quan.html', 'chart-theme.js', 'index.html', 'du-bao.html', 'kich-ban.html', 'ban-do-nhiet.html', 'tram.html', 'so-sanh.html', 'canh-bao.html',
  'thong-ke.html', 'bao-cao.html', 'gioi-thieu.html', 'phuong-phap.html', 'iot.html', 'iot-layer.js', 'phan-anh.html', 'phan-anh-layer.js', 'tai-app.html', 'tra-cuu-khong-gian.html', 'hoa-gio.html', 'trang-thai-du-lieu.html', 'login.html', 'tai-khoan.html', 'chinh-sach-rieng-tu.html',
  'style.css', 'app-config.js', 'aqi-vn.js', 'song-truc-tiep.js', 'tro-ly.js', 'pwa.js', 'nav.js', 'thong-bao-day.js',
  'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'];
const CDN = ['cdnjs.cloudflare.com', 'cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'];

// Phản hồi riêng tư (dữ liệu của người đăng nhập) không được lưu lại trên máy
const duocLuu = r => r.ok && !/no-store|private/i.test(r.headers.get('Cache-Control') || '');

self.addEventListener('install', e => {
  e.waitUntil(caches.open(PHIEN_BAN).then(c => Promise.all(LOI.map(u => c.add(u).catch(() => null)))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== PHIEN_BAN).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.pathname.indexOf('/api/v1/auth/') >= 0) return;               // không bao giờ lưu đăng nhập/phiên
  if (url.pathname.indexOf('/api/v1/su-kien') >= 0 || (req.headers.get('accept') || '').indexOf('text/event-stream') >= 0) return;   // luồng SSE: để trình duyệt tự xử lý
  if (url.pathname.indexOf('/api/v1/tro-ly') >= 0) return;            // trợ lý AI: không lưu
  if (url.pathname.indexOf('/api/') >= 0) {                              // API: mạng trước, mất mạng thì dùng bản gần nhất
    e.respondWith(fetch(req).then(r => { if (duocLuu(r)) { const cp = r.clone(); caches.open(PHIEN_BAN).then(c => c.put(req, cp)); } return r; })
      .catch(() => caches.match(req).then(m => m || new Response(JSON.stringify({ detail: 'Đang ngoại tuyến và chưa có dữ liệu lưu.' }), { status: 503, headers: { 'Content-Type': 'application/json' } }))));
    return;
  }
  if (url.origin === location.origin) {   // trang và mã của web: mạng trước (luôn thấy bản mới), mất mạng mới dùng bản lưu
    e.respondWith(fetch(req).then(r => { if (duocLuu(r)) { const cp = r.clone(); caches.open(PHIEN_BAN).then(c => c.put(req, cp)); } return r; })
      .catch(() => caches.match(req).then(m => m || caches.match('index.html'))));
    return;
  }
  if (CDN.indexOf(url.hostname) >= 0) {   // thư viện CDN (đã ghim phiên bản): dùng bản lưu ngay, cập nhật nền
    e.respondWith(caches.match(req).then(m => {
      const mang = fetch(req).then(r => { if (r.ok) { const cp = r.clone(); caches.open(PHIEN_BAN).then(c => c.put(req, cp)); } return r; }).catch(() => m);
      return m || mang;
    }));
  }
});

// ===== Thông báo đẩy (máy chủ gửi qua Web Push, xem backend/services/day_thong_bao.py) =====
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { tieu_de: 'AirHCM', noi_dung: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.tieu_de || 'AirHCM – Cảnh báo không khí', {
    body: d.noi_dung || '',
    icon: 'icons/icon-192.png',
    badge: 'icons/favicon-32.png',
    tag: d.tag || 'airhcm-aqi',          // cùng tag: thông báo mới thay thông báo cũ, không chất đống
    renotify: true,
    requireInteraction: !!d.quan_trong,
    data: { url: d.url || 'tong-quan.html' },
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const dich = new URL(e.notification.data && e.notification.data.url || 'tong-quan.html', self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(ds => {
    for (const c of ds) { if (c.url.indexOf(self.registration.scope) === 0 && 'focus' in c) { c.navigate(dich); return c.focus(); } }
    return self.clients.openWindow(dich);
  }));
});
// Trình duyệt tự đổi khóa đăng ký: báo máy chủ đăng ký lại bằng khóa mới
self.addEventListener('pushsubscriptionchange', e => {
  e.waitUntil(fetch('api/v1/day/khoa-cong-khai').then(r => r.json()).then(k =>
    self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: k.khoa })).then(sub =>
    fetch('api/v1/day/dang-ky', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dang_ky: sub.toJSON(), cu: e.oldSubscription && e.oldSubscription.endpoint }) })).catch(() => {}));
});
