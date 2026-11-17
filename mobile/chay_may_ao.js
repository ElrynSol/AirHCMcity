// Mở máy ảo Android, cài AirHCM.apk và chạy app: npm run may-ao
// Tùy chọn: node chay_may_ao.js <tên máy ảo>   (xem danh sách: emulator -list-avds)
// Cắm điện thoại thật (bật Gỡ lỗi USB) thì script cài thẳng vào điện thoại, không mở máy ảo.
const { execFileSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || path.join(process.env.LOCALAPPDATA || '', 'Android', 'Sdk');
const exe = process.platform === 'win32' ? '.exe' : '';
const adb = path.join(sdk, 'platform-tools', 'adb' + exe);
const emulator = path.join(sdk, 'emulator', 'emulator' + exe);
const apk = path.join(__dirname, 'AirHCM.apk');
const APP = 'vn.edu.aqi.hcm';

const ngu = ms => new Promise(r => setTimeout(r, ms));
const adbRa = (...a) => { try { return execFileSync(adb, a, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch (e) { return ''; } };
const thietBi = () => adbRa('devices').split('\n').slice(1).filter(d => /\tdevice$/.test(d)).map(d => d.split('\t')[0]);

(async () => {
  if (!fs.existsSync(apk)) { console.error('Chưa có AirHCM.apk — chạy "npm run apk" trước.'); process.exit(1); }
  let ds = thietBi();
  if (!ds.length) {
    const avd = process.argv[2] || execFileSync(emulator, ['-list-avds'], { encoding: 'utf8' }).trim().split(/\r?\n/)[0];
    if (!avd) { console.error('Chưa có máy ảo. Tạo trong Android Studio → Device Manager.'); process.exit(1); }
    console.log('Đang mở máy ảo', avd, '...');
    spawn(emulator, ['-avd', avd, '-no-snapshot-save', '-no-boot-anim'], { detached: true, stdio: 'ignore' }).unref();
    for (let i = 0; i < 120 && !ds.length; i++) { await ngu(2000); ds = thietBi(); }
  }
  const may = ds[0];
  if (!may) { console.error('Không thấy thiết bị nào.'); process.exit(1); }
  console.log('Thiết bị:', may, '— chờ khởi động xong...');
  for (let i = 0; i < 150 && adbRa('-s', may, 'shell', 'getprop', 'sys.boot_completed') !== '1'; i++) await ngu(2000);
  console.log('Cài APK...');
  execFileSync(adb, ['-s', may, 'install', '-r', apk], { stdio: 'inherit' });
  adbRa('-s', may, 'shell', 'monkey', '-p', APP, '-c', 'android.intent.category.LAUNCHER', '1');
  console.log('Đã mở app AirHCM trên', may);
})();
