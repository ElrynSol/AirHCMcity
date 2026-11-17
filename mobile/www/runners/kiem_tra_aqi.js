// Tác vụ nền của app Android AirHCM (plugin @capacitor/background-runner).
// Hệ điều hành gọi sự kiện 'kiemTraAQI' định kỳ (cấu hình 30 phút trong capacitor.config.json; Android tối thiểu 15 phút,
// thời điểm thực tế do hệ điều hành quyết định để tiết kiệm pin) — kể cả khi app đã đóng.
// Môi trường chạy là JavaScript không giao diện: chỉ có fetch, CapacitorKV (lưu chuỗi), CapacitorNotifications.
// Mỗi lần gọi là một ngữ cảnh mới: trạng thái phải lưu trong CapacitorKV.

var NHAC_LAI_MS = 6 * 3600 * 1000;   // vẫn vượt ngưỡng thì nhắc lại tối đa 1 lần / 6 giờ

function doc(khoa, macDinh) {
  try { var v = CapacitorKV.get(khoa); return v && v.value ? v.value : macDinh; } catch (e) { return macDinh; }
}

// Màn hình khởi động (www/index.html) gửi địa chỉ máy chủ + ngưỡng sau khi kết nối thành công
addEventListener('luuCauHinh', function (resolve, reject, args) {
  try {
    if (args && args.url) CapacitorKV.set('may_chu', String(args.url));
    if (args && args.nguong) CapacitorKV.set('nguong', String(args.nguong));
    resolve();
  } catch (e) { reject(e); }
});

addEventListener('kiemTraAQI', async function (resolve, reject) {
  try {
    var mayChu = doc('may_chu', '');
    if (!mayChu) { resolve(); return; }
    var mang = CapacitorDevice.getNetworkStatus();
    if (mang && mang.connected === false) { resolve(); return; }

    var r = await fetch(mayChu + '/api/v1/day/aqi-hien-tai');
    if (!r.ok) { resolve(); return; }
    var d = await r.json();
    var aqi = Number(d.aqi), nguong = Number(doc('nguong', '101'));
    var dangVuot = doc('dang_vuot', '0') === '1', lanCuoi = Number(doc('lan_bao', '0'));

    if (aqi >= nguong) {
      if (!dangVuot || Date.now() - lanCuoi > NHAC_LAI_MS) {
        CapacitorNotifications.schedule([{
          id: 1001,
          title: 'AQI TP.HCM ' + aqi + ' – ' + (d.muc || 'vượt ngưỡng'),
          body: 'Chất chính: ' + (d.chat || '?') + ', PM2.5 ' + (d.pm25 != null ? d.pm25 : '?') + ' µg/m³.',
          largeBody: (d.khuyen_nghi || '') + ' (cập nhật ' + (d.cap_nhat || '') + ')',
          autoCancel: true,
        }]);
        CapacitorKV.set('lan_bao', String(Date.now()));
      }
      CapacitorKV.set('dang_vuot', '1');
    } else if (aqi < nguong - 10) {
      CapacitorKV.set('dang_vuot', '0');     // xuống hẳn dưới ngưỡng: lần vượt sau sẽ báo ngay
    }
    resolve();
  } catch (e) {
    reject(e);
  }
});
