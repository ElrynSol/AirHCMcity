/* Cấu hình địa chỉ máy chủ API cho web, PWA và app đóng gói (Capacitor).
   - Chạy qua backend (http://localhost:8000 hoặc http://IP-máy:8000) → dùng chính địa chỉ đó (cùng nguồn, cookie đăng nhập hoạt động).
   - Mở bằng Live Server (cổng khác) → trỏ về cổng 8000 của cùng máy.
   - App Capacitor (APK/IPA) → dùng SERVER_URL_CHO_APP (sửa dòng dưới) hoặc giá trị lưu trong localStorage 'api_origin'. */
(function () {
  var SERVER_URL_CHO_APP = 'http://192.168.1.10:8000';   // ĐỔI thành IP máy chạy backend (hoặc https://ten-mien-cua-ban) trước khi build app
  var p = location.protocol, h = location.hostname, port = location.port, o;
  var native = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) || p === 'capacitor:' || p === 'file:' || p === 'ionic:';
  if (native) { try { o = localStorage.getItem('api_origin'); } catch (e) {} o = o || SERVER_URL_CHO_APP; }
  // Chỉ khi mở bằng Live Server (cổng 5500/5501) hoặc mở tệp trực tiếp mới trỏ sang máy chủ cổng 8000;
  // còn lại web luôn do chính máy chủ AirHCM phục vụ → dùng cùng nguồn (chạy được ở mọi cổng, mọi tên miền).
  else if (port === '5500' || port === '5501' || p === 'file:') o = 'http://' + (h || 'localhost') + ':8000';
  else o = location.origin;
  window.API_ORIGIN = o;
  window.LA_APP_NATIVE = native;
  // Các trang cũ viết cứng 'http://localhost:8000/...': chuyển hướng sang địa chỉ máy chủ đúng mà không phải sửa từng chỗ.
  if (o !== 'http://localhost:8000' && window.fetch) {
    var f = window.fetch.bind(window);
    window.fetch = function (u, opt) {
      if (typeof u === 'string' && u.indexOf('http://localhost:8000') === 0) u = o + u.slice('http://localhost:8000'.length);
      return f(u, opt);
    };
  }
})();
