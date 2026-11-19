/* Đăng ký service worker cho chế độ PWA. */
(function () {
  if (window.LA_APP_NATIVE) return;
  var h = location.hostname, an = location.protocol === 'https:' || h === 'localhost' || h === '127.0.0.1';
  if ('serviceWorker' in navigator && an) navigator.serviceWorker.register('sw.js?v=20').catch(function () {});
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    window. deferredInstallPrompt = e;
  });
})();
