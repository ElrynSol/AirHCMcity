/* AirLive — nhận sự kiện thời gian thực từ máy chủ bằng Server-Sent Events (EventSource) + thông báo trình duyệt.
   Dùng:
     AirLive.nghe('iot.da_nhan', d => ...)      // tự mở kết nối; trình duyệt tự nối lại khi rớt mạng
     AirLive.chiBao(el)                         // chấm "● Trực tiếp" / "Đang nối lại…"
     AirLive.nutThongBao(el)                    // nút bật/tắt thông báo hệ điều hành khi vượt ngưỡng
   Chủ đề công khai: iot.da_nhan, iot.vuot_nguong, du_lieu.da_nap, dong_bo.xong (xem backend/core/day_su_kien.py).
   Đã bật thông báo thì trang nào có nav.js cũng tự kết nối để báo (kể cả khi tab đang ẩn). */
(function () {
  if (window.AirLive) return;
  var API = (window.API_ORIGIN || '') + '/api/v1';
  var CHU_DE = ['iot.da_nhan', 'iot.vuot_nguong', 'du_lieu.da_nap', 'dong_bo.xong'];
  var KHOA_TB = 'airhcm_thong_bao';
  var es = null, nguoiNghe = {}, ttNghe = [], tt = 'chua';
  var coThongBao = 'Notification' in window && !/AirHCM-App/.test(navigator.userAgent);   // WebView Android không hỗ trợ

  function datTT(x) { if (tt === x) return; tt = x; ttNghe.forEach(function (f) { try { f(x); } catch (e) {} }); }

  function mo() {
    if (es || !window.EventSource) return;
    es = new EventSource(API + '/su-kien');
    /* Máy chủ chủ động đóng luồng mỗi 25 giây (để nạp lại/khởi động lại không bị kẹt), trình duyệt nối lại sau 1 giây:
       chỉ báo "Đang nối lại" khi 4 giây vẫn chưa nối được, tránh nhấp nháy. Luồng bị đóng hẳn (máy chủ tắt, lỗi HTTP)
       thì tự mở lại sau 5 giây thay vì đứng yên ở "Ngoại tuyến". */
    var hen = null, nay = es;
    var song = function () { clearTimeout(hen); hen = null; datTT('song'); };
    es.addEventListener('ket_noi', song);
    es.onopen = song;
    es.onerror = function () {
      if (nay.readyState === 2) { clearTimeout(hen); datTT('tat'); nay.close(); if (es === nay) es = null; setTimeout(mo, 5000); return; }
      if (!hen) hen = setTimeout(function () { hen = null; if (es === nay && nay.readyState !== 1) datTT('noi_lai'); }, 4000);
    };
    CHU_DE.forEach(function (cd) {
      es.addEventListener(cd, function (ev) {
        var d = {};
        try { d = JSON.parse(ev.data); } catch (e) {}
        (nguoiNghe[cd] || []).forEach(function (f) { try { f(d); } catch (e) { console.error(e); } });
        xuLyChung(cd, d);
      });
    });
  }

  function nghe(cd, f) { (nguoiNghe[cd] = nguoiNghe[cd] || []).push(f); mo(); }

  /* ---------- Thông báo nhỏ trên trang ---------- */
  function toast(html, mau, ms) {
    var hop = document.getElementById('airlive-toast');
    if (!hop) {
      hop = document.createElement('div'); hop.id = 'airlive-toast'; hop.setAttribute('aria-live', 'polite');
      hop.style.cssText = 'position:fixed;top:calc(var(--header-h,56px) + 12px);right:12px;z-index:3000;display:flex;flex-direction:column;gap:8px;max-width:min(360px,calc(100vw - 24px))';
      document.body.appendChild(hop);
    }
    var t = document.createElement('div');
    t.style.cssText = 'background:#fff;border:1px solid #e4e8ef;border-left:5px solid ' + (mau || '#1b63d6') +
      ';border-radius:12px;padding:10px 14px;box-shadow:0 12px 30px rgba(15,23,42,.18);font:500 13.5px/1.5 var(--font,sans-serif);color:#101828;' +
      'opacity:0;transform:translateY(-6px);transition:opacity .25s,transform .25s';
    t.innerHTML = html;
    hop.appendChild(t);
    requestAnimationFrame(function () { t.style.opacity = 1; t.style.transform = 'none'; });
    setTimeout(function () { t.style.opacity = 0; setTimeout(function () { t.remove(); }, 300); }, ms || 7000);
  }

  /* ---------- Thông báo hệ điều hành ---------- */
  function thongBaoDangBat() {
    try { return coThongBao && localStorage.getItem(KHOA_TB) === '1' && Notification.permission === 'granted'; } catch (e) { return false; }
  }
  function hienThongBao(tieuDe, noiDung, the) {
    if (!thongBaoDangBat()) return;
    var opt = { body: noiDung, icon: 'icons/icon-192.png', badge: 'icons/favicon-32.png', tag: the || 'airhcm', renotify: true };
    // Android Chrome bắt buộc dùng service worker; máy tính dùng được Notification trực tiếp
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then(function (r) { r.showNotification(tieuDe, opt); }).catch(function () {});
    } else {
      try { new Notification(tieuDe, opt); } catch (e) {}
    }
  }
  function batThongBao() {
    if (!coThongBao) return Promise.resolve('khong_ho_tro');
    return Promise.resolve(Notification.requestPermission()).then(function (q) {
      try { localStorage.setItem(KHOA_TB, q === 'granted' ? '1' : '0'); } catch (e) {}
      if (q === 'granted') { mo(); hienThongBao('AirHCM', 'Đã bật thông báo khi chất lượng không khí vượt ngưỡng.', 'airhcm-bat'); }
      return q;
    });
  }
  function tatThongBao() { try { localStorage.setItem(KHOA_TB, '0'); } catch (e) {} }

  /* ---------- Xử lý chung cho mọi trang ---------- */
  function xuLyChung(cd, d) {
    var m = window.AQI_VN ? AQI_VN.muc(d.aqi) : { mau: '#dc2626', ten: '' };
    if (cd === 'iot.vuot_nguong') {
      toast('⚠️ <b>Trạm IoT ' + String(d.ma || '').replace(/[<>&"]/g, '') + '</b>: AQI <b>' + d.aqi + '</b> (' + m.ten + ') vượt ngưỡng ' + d.nguong +
            '. <a href="iot.html">Xem</a>', m.mau, 10000);
      hienThongBao('⚠️ AQI ' + d.aqi + ' – ' + m.ten, 'Trạm IoT ' + d.ma + ' vượt ngưỡng cảnh báo ' + d.nguong + '. Hạn chế hoạt động ngoài trời.', 'iot-' + d.ma);
    } else if (cd === 'dong_bo.xong' && d.trang_thai) {
      toast((d.trang_thai === 'thanh_cong' ? '✅' : '⚠️') + ' Đồng bộ dữ liệu xong: ' + (d.so_dong_openmeteo || 0) + ' dòng PM/thời tiết, ' +
            (d.so_dong_gee || 0) + ' dòng vệ tinh.', d.trang_thai === 'thanh_cong' ? '#16a34a' : '#f59e0b');
    }
  }

  /* ---------- Thành phần giao diện ---------- */
  function chiBao(el) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (!el) return;
    var ve = function (x) {
      el.innerHTML = x === 'song' ? '<i class="cham-song"></i>Trực tiếp' : x === 'noi_lai' ? '<i class="cham-song cho"></i>Đang nối lại…' : '<i class="cham-song tat"></i>Ngoại tuyến';
      el.title = x === 'song' ? 'Đang nhận dữ liệu thời gian thực từ máy chủ (Server-Sent Events)' : '';
    };
    ttNghe.push(ve); ve(tt === 'chua' ? 'noi_lai' : tt); mo();
  }
  function nutThongBao(el) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (!el) return;
    if (!coThongBao) { el.style.display = 'none'; return; }
    var ve = function () {
      var bat = thongBaoDangBat(), chan = Notification.permission === 'denied';
      el.innerHTML = bat ? '🔔 Đang bật thông báo' : chan ? '🔕 Trình duyệt đang chặn thông báo' : '🔔 Báo cho tôi khi vượt ngưỡng';
      el.setAttribute('aria-pressed', String(bat));
      el.disabled = chan;
      el.title = chan ? 'Mở cài đặt trang web của trình duyệt để cho phép thông báo' : bat ? 'Bấm để tắt' : 'Hiện thông báo của hệ điều hành khi trạm vượt ngưỡng cảnh báo';
    };
    el.onclick = function () { if (thongBaoDangBat()) { tatThongBao(); ve(); } else batThongBao().then(ve); };
    ve();
  }

  var css = document.createElement('style');
  css.textContent = '.cham-song{display:inline-block;width:8px;height:8px;border-radius:50%;background:#16a34a;margin-right:6px;vertical-align:1px;animation:nhipSong 1.6s infinite}' +
    '.cham-song.cho{background:#f59e0b;animation:none}.cham-song.tat{background:#98a2b3;animation:none}' +
    '@keyframes nhipSong{0%{box-shadow:0 0 0 0 rgba(22,163,74,.5)}70%{box-shadow:0 0 0 8px rgba(22,163,74,0)}100%{box-shadow:0 0 0 0 rgba(22,163,74,0)}}' +
    '@media (prefers-reduced-motion: reduce){.cham-song{animation:none}}';
  document.head.appendChild(css);

  window.AirLive = { nghe: nghe, chiBao: chiBao, nutThongBao: nutThongBao, toast: toast, batThongBao: batThongBao,
                     thongBaoDangBat: thongBaoDangBat, coThongBao: coThongBao, trangThai: function () { return tt; } };
  if (thongBaoDangBat()) mo();      // đã bật thông báo: trang nào cũng nghe để báo kịp
})();
