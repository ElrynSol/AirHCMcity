/* Thanh điều hướng dùng chung cho toàn bộ hệ thống AirHCM. */
(function () {
  var NHOM = [
    { ten: 'Tổng quan', href: 'tong-quan.html' },
    { ten: 'Bản đồ giám sát', muc: [
      ['index.html', 'Bản đồ trực tuyến AQI'],
      ['ban-do-nhiet.html', 'Bản đồ 168 phường/xã'],
      ['tra-cuu-khong-gian.html', 'Tra cứu bán kính & Đa giác'],
      ['hoa-gio.html', 'Phân tích hướng gió']] },
    { ten: 'Dự báo & Thống kê', muc: [
      ['du-bao.html', 'Dự báo 24 giờ & 7 ngày'],
      ['kich-ban.html', 'Mô phỏng kịch bản thời tiết'],
      ['thong-ke.html', 'Thống kê lịch sử'],
      ['so-sanh.html', 'So sánh khu vực'],
      ['bao-cao.html', 'Xuất báo cáo PDF / Excel']] },
    { ten: 'Cảnh báo & Cộng đồng', muc: [
      ['canh-bao.html', 'Đăng ký nhận cảnh báo'],
      ['phan-anh.html', 'Phản ánh điểm ô nhiễm'],
      ['tai-app.html', 'Ứng dụng Android (APK)']] },
    { ten: 'Hồ sơ đề tài', muc: [
      ['gioi-thieu.html', 'Giới thiệu & Kiến trúc'],
      ['phuong-phap.html', 'Phương pháp & Độ chính xác']] },
    { ten: 'Quản trị', muc: [
      ['tram.html', 'Quản lý điểm dữ liệu', true],
      ['trang-thai-du-lieu.html', 'Đồng bộ & Trạng thái dữ liệu', true],
      ['luong-canh-bao.html', 'Giám sát luồng cảnh báo', true],
      ['nhat-ky.html', 'Nhật ký hệ thống', true]] }
  ];
  var hd = document.getElementById('header');
  if (!hd || !hd.firstElementChild) return;
  var admin = false;
  try { admin = localStorage.getItem('vai_tro') === 'admin'; } catch (e) {}
  var trang = (location.pathname.split('/').pop() || 'index.html');
  var box = hd.firstElementChild;
  box.innerHTML = '';
  box.classList.add('nav-gon');

  var brand = document.createElement('a');
  brand.className = 'nav-brand'; brand.href = 'tong-quan.html';
  brand.innerHTML = '<img src="icons/favicon-32.png" alt=""><span>AirHCM<small>Giám sát &amp; Dự báo Không khí TP.HCM</small></span>';
  hd.insertBefore(brand, box);

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
    var ds = document.createElement('div'); ds.className = 'nav-ds';
    n.muc.forEach(function (m) {
      if (m[2] && !admin) return;
      var a = document.createElement('a');
      a.href = m[0]; a.textContent = m[1];
      if (m[0] === trang) a.className = 'nav-hien';
      ds.appendChild(a);
    });
    if (!ds.children.length) return;
    var w = document.createElement('div'); w.className = 'nav-nhom';
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'nav-nut' + (dang ? ' nav-hien' : '');
    b.textContent = n.ten + ' ▾';
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

  // Thanh điều hướng dưới đáy cho màn hình di động (dùng SVG phẳng đơn sắc)
  var TAB = [
    ['tong-quan.html', '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 10.5 12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/></svg>', 'Tổng quan'],
    ['index.html', '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/></svg>', 'Bản đồ'],
    ['du-bao.html', '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>', 'Dự báo'],
    ['canh-bao.html', '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>', 'Cảnh báo']
  ];
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
  nutThem.innerHTML = '<span class="tab-bt" aria-hidden="true">☰</span><span>Menu</span>';
  nutThem.onclick = function (e) { nutMenu.onclick(e); };
  thanhTab.appendChild(nutThem);
  document.body.appendChild(thanhTab);
  document.body.classList.add('co-tab-duoi');

  if (/AirHCM-App/.test(navigator.userAgent)) {
    document.body.classList.add('trong-app');
    var dsHeThong = box.querySelectorAll('.nav-ds');
    if (dsHeThong.length) {
      var doiMay = document.createElement('a');
      doiMay.href = 'http://localhost/?doi_may_chu=1';
      doiMay.textContent = 'Đổi máy chủ kết nối';
      dsHeThong[dsHeThong.length - 1].appendChild(doiMay);
    }
  }

  // Nút mở trợ lý tra cứu (dùng SVG phẳng thay vì emoji)
  if (!/login\.html$/.test(location.pathname)) {
    var bongNoi = document.createElement('button');
    bongNoi.type = 'button'; bongNoi.className = 'tl-bong-noi'; bongNoi.setAttribute('aria-label', 'Mở trợ lý tra cứu AirHCM');
    bongNoi.innerHTML = '<span class="tbn-icon" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></span><span class="tbn-dong" aria-hidden="true">✕</span>';
    bongNoi.onclick = function () {
      if (window.TroLy) { window.TroLy.batTat(); return; }
      bongNoi.classList.add('dang-nap');
      var s = document.createElement('script'); s.src = 'tro-ly.js?v=22';
      s.onload = function () { bongNoi.classList.remove('dang-nap'); window.TroLy && window.TroLy.mo(); };
      document.body.appendChild(s);
    };
    document.body.appendChild(bongNoi);
    if (/[?&]tro-ly\b/.test(location.search)) setTimeout(function () { bongNoi.click(); }, 300);
  }

  try {
    if (!window.AirLive && localStorage.getItem('airhcm_thong_bao') === '1') {
      var sl = document.createElement('script'); sl.src = 'song-truc-tiep.js?v=22'; document.body.appendChild(sl);
    }
  } catch (e) {}

  var userBox = document.getElementById('userBox');
  if (userBox && !/login\.html$/.test(location.pathname)) {
    var veHop = function (u) {
      userBox.textContent = '';
      if (u) {
        var tk = document.createElement('a');
        tk.href = 'tai-khoan.html'; tk.className = 'hop-tk';
        tk.title = 'Tài khoản & bảo mật';
        var ten = document.createElement('span'); ten.className = 'hop-tk-ten';
        ten.textContent = u.ho_ten + (u.vai_tro === 'admin' ? ' (Quản trị)' : '');
        tk.appendChild(ten);
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
        var di = function () { location.href = 'login.html'; };
        if (window.caches && caches.keys) caches.keys().then(function (ks) { return Promise.all(ks.map(function (k) { return caches.delete(k); })); }).then(di, di);
        else di();
      };
      fetch((window.API_ORIGIN || '') + '/api/v1/auth/logout', { method: 'POST', credentials: 'include' }).then(xong, xong);
    };
    fetch((window.API_ORIGIN || '') + '/api/v1/auth/me', { credentials: 'include', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return undefined; })
      .then(function (u) {
        if (u === undefined) return;
        try {
          if (u) {
            var cu = localStorage.getItem('vai_tro');
            localStorage.setItem('ho_ten', u.ho_ten); localStorage.setItem('vai_tro', u.vai_tro);
            if (cu !== u.vai_tro) location.reload();
          } else {
            localStorage.removeItem('ho_ten'); localStorage.removeItem('vai_tro');
          }
        } catch (e) {}
        veHop(u);
      });
  }

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

  if (trang !== 'index.html' && !document.querySelector('.chan-trang')) {
    var ft = document.createElement('footer');
    ft.className = 'chan-trang'; ft.setAttribute('role', 'contentinfo');
    var thang = (window.AQI_VN ? AQI_VN.THANG : []).map(function (m) { return '<span style="background:' + m.mau + '" title="' + m.ten + '"></span>'; }).join('');
    ft.innerHTML = '<div class="ct-trong">' +
      '<div><h4>AirHCM · Hệ thống Giám sát, Quản lý &amp; Dự báo Chất lượng Không khí TP.HCM</h4><p>Đồ án chuyên ngành Công nghệ thông tin môi trường. Cung cấp thông tin theo dõi hiện trạng, dự báo ngắn hạn và cảnh báo sớm chất lượng không khí trên địa bàn TP.HCM.</p></div>' +
      '<div><h4>Tiêu chuẩn áp dụng</h4><p>Chỉ số <b>VN_AQI (QĐ 1459/QĐ-TCMT)</b> và Quy chuẩn kỹ thuật quốc gia <b>QCVN 05:2023/BTNMT</b>.</p><div class="ct-thang">' + thang + '</div></div>' +
      '<div><h4>Tài liệu &amp; Liên kết</h4><p>Dữ liệu tích hợp từ Open-Meteo (CAMS/ERA5), Sentinel-5P và OpenAQ.<br><a href="phuong-phap.html">Phương pháp &amp; Độ chính xác</a> · <a href="tai-app.html">Ứng dụng di động</a> · <a href="gioi-thieu.html">Giới thiệu</a> · <a href="chinh-sach-rieng-tu.html">Quyền riêng tư</a></p></div>' +
      '</div><div class="ct-cuoi">© ' + new Date().getFullYear() + ' AirHCM · Lê Ngọc Ánh Dương (MSSV 1250080037) · GVHD: TS. Dương Thị Thúy Nga</div>';
    document.body.appendChild(ft);
  }
})();
