/* Đăng ký service worker + nút "Cài app". Service worker chỉ chạy trên HTTPS hoặc localhost (quy định của trình duyệt). */
(function () {
  if (window.LA_APP_NATIVE) return;
  var h = location.hostname, an = location.protocol === 'https:' || h === 'localhost' || h === '127.0.0.1';
  if ('serviceWorker' in navigator && an) navigator.serviceWorker.register('sw.js').catch(function () {});
  var hoan = null;
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault(); hoan = e;
    var b = document.createElement('button');
    b.textContent = '📲 Cài app'; b.className = 'nut-cai-app';
    b.style.cssText = 'position:fixed;right:14px;bottom:calc(14px + (var(--tab-h, 0px) * var(--co-tab, 0)));z-index:5000;padding:10px 16px;border:none;border-radius:22px;background:#1a73e8;color:#fff;font-weight:700;box-shadow:0 4px 14px rgba(0,0,0,.25);cursor:pointer;';
    b.onclick = function () { hoan.prompt(); hoan.userChoice.finally(function () { b.remove(); hoan = null; }); };
    document.body.appendChild(b);
  });
})();
