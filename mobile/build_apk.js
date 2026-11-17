// Build APK debug: npm run apk  →  mobile/AirHCM.apk   (Windows, macOS, Linux)
// Cần: Android SDK (ANDROID_HOME, hoặc vị trí mặc định của Android Studio) và JDK 21+ (JAVA_HOME).
// Máy chủ công khai app thử đầu tiên: biến môi trường AIRHCM_URL=https://... hoặc TEN_MIEN trong ../.env
const { execSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const macDinhSdk = process.platform === 'win32' ? path.join(process.env.LOCALAPPDATA || '', 'Android', 'Sdk')
  : process.platform === 'darwin' ? path.join(os.homedir(), 'Library', 'Android', 'sdk') : path.join(os.homedir(), 'Android', 'Sdk');
const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || macDinhSdk;
if (!fs.existsSync(sdk)) { console.error('Không thấy Android SDK tại', sdk, '- cài Android Studio hoặc đặt biến ANDROID_HOME.'); process.exit(1); }
const env = { ...process.env, ANDROID_HOME: sdk };
// Đường dẫn có dấu cách (vd. "Máy tính") phải đặt trong ngoặc kép
const chay = (lenh, cwd = __dirname) => { console.log('\n> ' + lenh); execSync(lenh, { cwd, env, stdio: 'inherit' }); };

// 1. Địa chỉ máy chủ công khai → www/may_chu.js
let url = (process.env.AIRHCM_URL || '').trim();
if (!url) {
  try {
    const m = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf8').match(/^TEN_MIEN=(.+)$/m);
    if (m && m[1].trim()) url = 'https://' + m[1].trim().replace(/^https?:\/\//, '');
  } catch (e) { /* chưa có .env */ }
}
url = url.replace(/\/+$/, '');
fs.writeFileSync(path.join(__dirname, 'www', 'may_chu.js'),
  '// Tự sinh bởi build_apk.js từ TEN_MIEN trong .env — địa chỉ máy chủ công khai app thử đầu tiên.\n' +
  'window.AIRHCM_MAY_CHU = ' + JSON.stringify(url ? [url] : []) + ';\n');
console.log(url ? 'Máy chủ công khai trong app: ' + url : 'Chưa có TEN_MIEN: app chỉ tìm máy chủ trong mạng Wi-Fi / máy ảo');

// 2. Build
fs.writeFileSync(path.join(__dirname, 'android', 'local.properties'), 'sdk.dir=' + sdk.replace(/\\/g, '/') + '\n');
chay('npx cap sync android');

// Android Gradle từ chối đường dẫn có ký tự ngoài ASCII (vd. "...\Máy tính\..."). Trên Windows: tạo ổ đĩa ảo tạm
// (subst) trỏ vào thư mục mobile/ để đường dẫn chỉ còn "X:\android", build xong thì gỡ ổ ảo — không đổi gì trong dự án.
let goc = __dirname, oAo = null;
if (process.platform === 'win32' && /[^\x00-\x7F]/.test(__dirname)) {
  const dangDung = execSync('subst', { encoding: 'utf8' }) + ' ';
  oAo = 'RSTUVWXYZ'.split('').map(c => c + ':').find(o => !fs.existsSync(o + '\\') && dangDung.indexOf(o) < 0);
  if (!oAo) { console.error('Không còn ký tự ổ đĩa trống để tạo ổ ảo. Hãy chuyển dự án sang thư mục chỉ có chữ không dấu.'); process.exit(1); }
  chay(`subst ${oAo} "${__dirname}"`);
  goc = oAo + '\\';
  console.log(`Đường dẫn có ký tự tiếng Việt → build qua ổ ảo ${oAo}`);
}
const thuMucAndroid = path.join(goc, 'android');
try {
  chay(process.platform === 'win32' ? '"' + path.join(thuMucAndroid, 'gradlew.bat') + '" assembleDebug' : './gradlew assembleDebug', thuMucAndroid);
} finally {
  if (oAo) {
    try { execSync(path.join(thuMucAndroid, 'gradlew.bat') + ' --stop', { cwd: thuMucAndroid, stdio: 'ignore' }); } catch (e) {}   // nhả khóa tệp trước khi gỡ ổ ảo
    try { execSync(`subst ${oAo} /D`); } catch (e) { console.warn('Gỡ ổ ảo thất bại, tự gỡ bằng: subst ' + oAo + ' /D'); }
  }
}

const apk = path.join(__dirname, 'android', 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk');
const dich = path.join(__dirname, 'AirHCM.apk');
fs.copyFileSync(apk, dich);
console.log('\nXong: ' + dich + ' (' + (fs.statSync(dich).size / 1048576).toFixed(1) + ' MB)');
