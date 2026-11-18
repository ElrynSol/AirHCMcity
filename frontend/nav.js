/* Menu gọn dùng chung: gom các trang thành 5 mục. Sửa menu ở MỘT chỗ này. */
(function () {
  var NHOM = [
    { ten: '🏠 Tổng quan', href: 'tong-quan.html' },
    { ten: '🗺️ Bản đồ', href: 'index.html' },
    { ten: '🔮 Dự báo', muc: [
      ['du-bao.html', '🔮 Dự báo theo giờ / ngày'],
      ['kich-ban.html', '🎛️ Kịch bản (đổi tham số)'],
      ['ban-do-nhiet.html', '🌡️ Bản đồ nhiệt dự báo']] },
    { ten: '📊 Phân tích', muc: [
      ['tra-cuu-khong-gian.html', '🧭 Tra cứu không gian'],
      ['so-sanh.html', '📊 So sánh các nơi'],
      ['hoa-gio.html', '🧭 Hoa gió ô nhiễm'],
      ['thong-ke.html', '📈 Thống kê'],
      ['bao-cao.html', '📄 Báo cáo']] },
    { ten: '⚠️ Cảnh báo', muc: [
      ['canh-bao.html', '⚠️ Cảnh báo hiện tại'],
      ['phan-anh.html', '📣 Phản ánh ô nhiễm'],
      ['luong-canh-bao.html', '🔔 Luồng cảnh báo']] },
    { ten: '⚙️ Hệ thống', muc: [
      ['tram.html', '📋 Danh sách điểm ước tính'],
      ['phuong-phap.html', '🔬 Phương pháp & kiểm chứng'],
      ['trang-thai-du-lieu.html', '🛰️ Trạng thái dữ liệu'],
      ['nhat-ky.html', '🧾 Nhật ký', true],
      ['tai-khoan.html', '🔐 Tài khoản & bảo mật'],
      ['tai-app.html', '📲 Tải ứng dụng'],
      ['gioi-thieu.html', 'ℹ️ Giới thiệu']] }
  ];
  var hd = document.getElementById('header');
  if (!hd || !hd.firstElementChild) return;
  var admin = false;
  try { admin = localStorage.getItem('vai_tro') === 'admin'; } catch (e) {}
  var trang = (location.pathname.split('/').pop() || 'index.html');
  var box = hd.firstElementChild;
  box.innerHTML = '';
  box.classList.add('nav-gon');

  // Logo + tên hệ thống ở đầu header
  var brand = document.createElement('a');
  brand.className = 'nav-brand'; brand.href = 'tong-quan.html';
  brand.innerHTML = '<img src="icons/favicon-32.png" alt=""><span>AirHCM<small>Giám sát không khí TP.HCM</small></span>';
  hd.insertBefore(brand, box);

  // Nút ☰ cho màn hình hẹp (CSS chỉ hiện khi ≤ 760px)
  var nutMenu = document.createElement('button');
  nutMenu.type = 'button'; nutMenu.className = 'nav-mo-btn';
  nutMenu.setAttribute('aria-label', 'Mở menu'); nutMenu.setAttribute('aria-expanded', 'false');
  nutMenu.textContent = '☰';
  nutMenu.onclick = function (e) {
    e.stopPropagation();
    var mo = hd.classList.toggle('menu-mo');
    nutMenu.textContent = mo ? '✕' : '☰';
    nutMenu.setAttribute('aria-expanded', String(mo));
  };
  hd.appendChild(nutMenu);
  box.addEventListener('click', function (e) { if (e.target.tagName === 'A') hd.classList.remove('menu-mo'); });
  var dong = function () {
    var m = document.querySelectorAll('.nav-nhom.mo');
    for (var i = 0; i < m.length; i++) m[i].classList.remove('mo');
  };
  NHOM.forEach(function (n) {
    var dang = n.href ? n.href === trang : n.muc.some(function (m) { return m[0] === trang; });
    if (n.href) {
      var a = document.createElement('a');
      a.href = n.href; a.textContent = n.ten;
      if (dang) a.className = 'nav-hien';
      box.appendChild(a); return;
    }
    var w = document.createElement('div'); w.className = 'nav-nhom';
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'nav-nut' + (dang ? ' nav-hien' : '');
    b.textContent = n.ten + ' ▾';
    var ds = document.createElement('div'); ds.className = 'nav-ds';
    n.muc.forEach(function (m) {
      if (m[2] && !admin) return;
      var a = document.createElement('a');
      a.href = m[0]; a.textContent = m[1];
      if (m[0] === trang) a.className = 'nav-hien';
      ds.appendChild(a);
    });
    b.onclick = function (e) {
      e.stopPropagation();
      var da = w.classList.contains('mo'); dong();
      if (!da) {
        w.classList.add('mo');
        var r = b.getBoundingClientRect();
        ds.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 250)) + 'px';
      }
    };
    w.appendChild(b); w.appendChild(ds); box.appendChild(w);
  });
  document.addEventListener('click', function (e) {
    dong();
    if (!hd.contains(e.target) && hd.classList.contains('menu-mo')) { hd.classList.remove('menu-mo'); nutMenu.textContent = '☰'; }
  });
  window.addEventListener('scroll', function () { if (!hd.classList.contains('menu-mo')) dong(); }, true);
  window.addEventListener('resize', dong);

  // Thanh tab dưới đáy cho điện thoại (CSS chỉ hiện khi ≤ 760px): 4 trang dùng nhiều nhất + "Thêm" mở menu đầy đủ
  var TAB = [['tong-quan.html', '🏠', 'Tổng quan'], ['index.html', '🗺️', 'Bản đồ'], ['du-bao.html', '🔮', 'Dự báo'], ['canh-bao.html', '⚠️', 'Cảnh báo']];
  var thanhTab = document.createElement('nav');
  thanhTab.className = 'tab-duoi'; thanhTab.setAttribute('aria-label', 'Điều hướng nhanh');
  var coTab = false;
  TAB.forEach(function (t) {
    var a = document.createElement('a');
    a.href = t[0];
    if (t[0] === trang) { a.className = 'tab-hien'; a.setAttribute('aria-current', 'page'); coTab = true; }
    a.innerHTML = '<span class="tab-bt" aria-hidden="true">' + t[1] + '</span><span>' + t[2] + '</span>';
    thanhTab.appendChild(a);
  });
  var nutThem = document.createElement('button');
  nutThem.type = 'button'; nutThem.setAttribute('aria-label', 'Mở toàn bộ menu');
  if (!coTab) nutThem.className = 'tab-hien';
  nutThem.innerHTML = '<span class="tab-bt" aria-hidden="true">☰</span><span>Thêm</span>';
  nutThem.onclick = function (e) { nutMenu.onclick(e); };
  thanhTab.appendChild(nutThem);
  document.body.appendChild(thanhTab);
  document.body.classList.add('co-tab-duoi');

  // Đang chạy trong app Android (capacitor.config.json gắn "AirHCM-App" vào user agent)
  if (/AirHCM-App/.test(navigator.userAgent)) {
    document.body.classList.add('trong-app');
    var dsHeThong = box.querySelectorAll('.nav-ds');
    if (dsHeThong.length) {
      var doiMay = document.createElement('a');
      doiMay.href = 'http://localhost/?doi_may_chu=1';   // trang khởi động cục bộ của app
      doiMay.textContent = '🔌 Đổi máy chủ (app)';
      dsHeThong[dsHeThong.length - 1].appendChild(doiMay);
    }
  }

  // Bong bóng trợ lý AI nổi ở góc dưới phải (kiểu chat Messenger): bấm để bật/thu khung chat.
  // tro-ly.js chỉ nạp khi bấm lần đầu (không làm chậm lúc mở trang); trang đăng nhập không cần.
  if (!/login\.html$/.test(location.pathname)) {
    var bongNoi = document.createElement('button');
    bongNoi.type = 'button'; bongNoi.className = 'tl-bong-noi'; bongNoi.setAttribute('aria-label', 'Mở trợ lý AirHCM');
    bongNoi.innerHTML = '<span class="tbn-icon" aria-hidden="true">✨</span><span class="tbn-dong" aria-hidden="true">✕</span><i class="tbn-cham" aria-hidden="true"></i>';
    bongNoi.onclick = function () {
      if (chao) chao.remove();
      if (window.TroLy) { window.TroLy.batTat(); return; }
      bongNoi.classList.add('dang-nap');
      var s = document.createElement('script'); s.src = 'tro-ly.js';
      s.onload = function () { bongNoi.classList.remove('dang-nap'); window.TroLy && window.TroLy.mo(); };
      document.body.appendChild(s);
    };
    document.body.appendChild(bongNoi);
    if (/[?&]tro-ly\b/.test(location.search)) setTimeout(function () { bongNoi.click(); }, 300);   // liên kết mở sẵn trợ lý
    // Lời chào nhỏ cạnh bong bóng: mỗi phiên hiện 1 lần, tự ẩn sau 7 giây
    var chao = null;
    try {
      if (!sessionStorage.getItem('airhcm_da_chao')) {
        sessionStorage.setItem('airhcm_da_chao', '1');
        chao = document.createElement('div'); chao.className = 'tl-chao';
        chao.innerHTML = 'Hỏi mình về không khí hôm nay nhé 👋';
        chao.onclick = function () { bongNoi.click(); };
        setTimeout(function () { document.body.appendChild(chao); }, 1500);
        setTimeout(function () { if (chao) { chao.classList.add('an'); setTimeout(function () { chao && chao.remove(); chao = null; }, 400); } }, 8500);
      }
    } catch (e) {}
  }

  // Đã bật thông báo vượt ngưỡng: nạp bộ nhận sự kiện thời gian thực ở mọi trang (song-truc-tiep.js)
  try {
    if (!window.AirLive && localStorage.getItem('airhcm_thong_bao') === '1') {
      var sl = document.createElement('script'); sl.src = 'song-truc-tiep.js'; document.body.appendChild(sl);
    }
  } catch (e) {}

  // Hộp tài khoản (góc phải header) dùng chung cho mọi trang: hỏi máy chủ phiên còn hiệu lực không (/auth/me)
  // thay vì tin localStorage → phiên hết hạn/bị đăng xuất từ thiết bị khác thì giao diện cập nhật đúng.
  // Dựng bằng textContent (không innerHTML) để họ tên không chèn được mã độc.
  var userBox = document.getElementById('userBox');
  if (userBox && !/login\.html$/.test(location.pathname)) {
    var veHop = function (u) {
      userBox.textContent = '';
      if (u) {
        var tk = document.createElement('a');
        tk.href = 'tai-khoan.html'; tk.className = 'hop-tk';
        tk.title = 'Tài khoản & bảo mật';
        var bt = document.createElement('i'); bt.className = 'hop-tk-bt'; bt.textContent = u.totp_bat ? '🔐' : '👤';
        var ten = document.createElement('span'); ten.className = 'hop-tk-ten';
        ten.textContent = u.ho_ten + (u.vai_tro === 'admin' ? ' · admin' : '');
        tk.appendChild(bt); tk.appendChild(ten);
        var ra = document.createElement('button');
        ra.type = 'button'; ra.textContent = 'Đăng xuất';
        ra.onclick = function () { window.dangXuat(); };
        userBox.appendChild(tk); userBox.appendChild(ra);
      } else {
        var vao = document.createElement('button');
        vao.type = 'button'; vao.textContent = 'Đăng nhập';
        vao.onclick = function () { location.href = 'login.html?tiep=' + encodeURIComponent(trang + location.search); };
        userBox.appendChild(vao);
      }
    };
    window.dangXuat = function () {
      var xong = function () {
        try { localStorage.removeItem('ho_ten'); localStorage.removeItem('vai_tro'); } catch (e) {}
        // Xóa dữ liệu đã lưu offline để người dùng sau trên máy dùng chung không xem được (service worker tự nạp lại phần giao diện)
        var di = function () { location.href = 'login.html'; };
        if (window.caches && caches.keys) caches.keys().then(function (ks) { return Promise.all(ks.map(function (k) { return caches.delete(k); })); }).then(di, di);
        else di();
      };
      fetch((window.API_ORIGIN || '') + '/api/v1/auth/logout', { method: 'POST', credentials: 'include' }).then(xong, xong);
    };
    fetch((window.API_ORIGIN || '') + '/api/v1/auth/me', { credentials: 'include', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return undefined; })   // mất mạng: giữ nguyên giao diện hiện có
      .then(function (u) {
        if (u === undefined) return;
        try {
          if (u) { localStorage.setItem('ho_ten', u.ho_ten); localStorage.setItem('vai_tro', u.vai_tro); }
          else { localStorage.removeItem('ho_ten'); localStorage.removeItem('vai_tro'); }
        } catch (e) {}
        veHop(u);
      });
  }

  // Truy cập bằng bàn phím: liên kết "bỏ qua menu" tới phần nội dung đầu tiên sau header
  var noiDung = hd.nextElementSibling;
  while (noiDung && /^(SCRIPT|STYLE)$/.test(noiDung.tagName)) noiDung = noiDung.nextElementSibling;
  if (noiDung) {
    if (!noiDung.id) noiDung.id = 'noi-dung';
    if (!noiDung.hasAttribute('tabindex')) noiDung.setAttribute('tabindex', '-1');
    var bq = document.createElement('a');
    bq.className = 'skip-link'; bq.href = '#' + noiDung.id; bq.textContent = 'Bỏ qua menu, tới nội dung';
    document.body.insertBefore(bq, document.body.firstChild);
  }
  hd.setAttribute('role', 'banner');
  box.setAttribute('role', 'navigation');
  box.setAttribute('aria-label', 'Menu chính');

  // Chân trang chuẩn web quan trắc: nguồn dữ liệu, căn cứ tính AQI, miễn trừ (trang bản đồ toàn màn hình thì bỏ qua)
  if (trang !== 'index.html' && !document.querySelector('.chan-trang')) {
    var ft = document.createElement('footer');
    ft.className = 'chan-trang'; ft.setAttribute('role', 'contentinfo');
    var thang = (window.AQI_VN ? AQI_VN.THANG : []).map(function (m) { return '<span style="background:' + m.mau + '" title="' + m.ten + '"></span>'; }).join('');
    ft.innerHTML = '<div class="ct-trong">' +
      '<div><h4>AirHCM · Giám sát chất lượng không khí TP.HCM</h4><p>Đồ án chuyên ngành Công nghệ thông tin môi trường. Số liệu là <b>ước tính phục vụ học thuật</b>, không thay thế số liệu quan trắc chính thức của cơ quan quản lý môi trường.</p></div>' +
      '<div><h4>Chỉ số AQI</h4><p>Tính theo <b>VN_AQI – QĐ 1459/QĐ-TCMT</b> từ PM2.5, PM10, O₃; ngưỡng nồng độ theo QCVN 05:2023/BTNMT.</p><div class="ct-thang">' + thang + '</div></div>' +
      '<div><h4>Nguồn dữ liệu</h4><p>Open-Meteo (mô hình CAMS, lưới ~45 km) · Sentinel-5P qua Google Earth Engine (NO₂, CO, SO₂ – cột khí, trễ 2–3 tuần).<br><a href="phuong-phap.html">Phương pháp &amp; kiểm chứng</a> · <a href="trang-thai-du-lieu.html">Tình trạng dữ liệu</a> · <a href="gioi-thieu.html">Giới thiệu</a> · <a href="chinh-sach-rieng-tu.html">Quyền riêng tư</a></p></div>' +
      '</div><div class="ct-cuoi">© ' + new Date().getFullYear() + ' AirHCM · Lê Ngọc Ánh Dương · GVHD: TS. Dương Thị Thúy Nga</div>';
    document.body.appendChild(ft);
  }
})();
