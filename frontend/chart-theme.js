/* Giao diện chung cho mọi biểu đồ Chart.js của AirHCM (nạp ngay sau chart.umd.min.js).
   - Font, màu chữ, lưới nhạt, chú giải dạng chấm tròn, hộp chú thích (tooltip) nền xanh đậm bo góc.
   - Plugin tùy chọn "nenAqi": tô nền 6 dải màu AQI (QĐ 1459) phía sau trục AQI:
       options: { plugins: { nenAqi: { truc: 'y2', doMo: 0.10 } } }
   Biểu đồ nào đã tự đặt thuộc tính riêng thì giữ nguyên (chỉ đổi giá trị mặc định). */
(function () {
  if (!window.Chart) return;
  var C = window.Chart, d = C.defaults;
  var font = (getComputedStyle(document.documentElement).getPropertyValue('--font') || '').trim() || "'Be Vietnam Pro', 'Segoe UI', sans-serif";

  d.font.family = font;
  d.font.size = 12;
  d.color = '#475467';
  d.borderColor = 'rgba(16, 24, 40, .07)';
  d.maintainAspectRatio = true;
  d.animation.duration = 650;
  d.animation.easing = 'easeOutQuart';

  d.elements.line.borderWidth = 2.2;
  d.elements.line.tension = d.elements.line.tension || 0.3;
  d.elements.point.radius = 0;
  d.elements.point.hoverRadius = 5;
  d.elements.point.hitRadius = 8;
  d.elements.bar.borderRadius = 6;
  d.elements.bar.borderSkipped = 'start';
  d.elements.arc.borderWidth = 2;

  var L = d.plugins.legend.labels;
  L.usePointStyle = true;
  L.pointStyle = 'circle';
  L.boxWidth = 8;
  L.boxHeight = 8;
  L.padding = 14;
  L.font = { size: 12, weight: '500' };

  var T = d.plugins.tooltip;
  T.backgroundColor = 'rgba(11, 37, 69, .94)';
  T.titleColor = '#fff';
  T.bodyColor = 'rgba(255, 255, 255, .88)';
  T.borderColor = 'rgba(255, 255, 255, .08)';
  T.borderWidth = 1;
  T.padding = 10;
  T.cornerRadius = 10;
  T.boxPadding = 4;
  T.usePointStyle = true;
  T.titleFont = { weight: '700', size: 12.5 };
  T.bodyFont = { size: 12 };

  // Trục: lưới ngang nhạt, bỏ lưới dọc của trục danh mục, chữ trục xám (gộp vào mặc định, không ghi đè cả object)
  if (typeof d.set === 'function') {
    d.set('scale', { grid: { color: 'rgba(16, 24, 40, .06)', drawTicks: false }, border: { display: false },
                     ticks: { padding: 8, color: '#667085' } });
    d.set('scales.category', { grid: { display: false } });
  }

  // Plugin nền dải màu AQI
  C.register({
    id: 'nenAqi',
    beforeDraw: function (chart, _args, opt) {
      if (!opt || !opt.truc || !window.AQI_VN) return;
      var y = chart.scales[opt.truc], area = chart.chartArea;
      if (!y || !area) return;
      var ctx = chart.ctx;
      ctx.save();
      ctx.globalAlpha = opt.doMo == null ? 0.10 : opt.doMo;
      window.AQI_VN.THANG.forEach(function (m) {
        var tren = Math.max(area.top, y.getPixelForValue(Math.min(m.den, y.max)));
        var duoi = Math.min(area.bottom, y.getPixelForValue(Math.max(m.tu, y.min)));
        if (duoi > tren && m.tu <= y.max) { ctx.fillStyle = m.mau; ctx.fillRect(area.left, tren, area.right - area.left, duoi - tren); }
      });
      ctx.restore();
    }
  });
})();
