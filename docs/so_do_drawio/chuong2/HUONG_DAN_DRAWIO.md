# Hướng dẫn mở, sửa và xuất sơ đồ Chương 2 bằng draw.io

Mỗi sơ đồ có hai bản cùng nội dung:
- `.drawio`: mở và sửa được trong draw.io.
- `.png`: ảnh để dán vào Word/WPS.

`AirHCM_Chuong2_TatCa_SoDo.drawio` gộp cả 8 sơ đồ, mỗi sơ đồ một trang (tab ở cuối màn hình).

| Tệp | Hình trong báo cáo | Căn cứ trong mã nguồn |
|---|---|---|
| 01_UseCase | Hình 2.1 | `require_admin`, `get_current_user` trong `backend/routers/*` |
| 02_KienTruc | Hình 2.2 | `data_pipeline/`, `backend/core`, `services`, `routers`, `ml/` |
| 03_ERD_17_bang | Hình 2.3 | `information_schema` của CSDL: 17 bảng, 13 khóa ngoại |
| 04_TuanTu_DangNhap | Hình 2.4 | `routers/auth.py` (`login`, `dang_nhap_2fa`), `core/phien.py` |
| 05_TuanTu_DuBao | Hình 2.5 | `routers/du_bao.py`, `ml/predict.py` |
| 06_HoatDong_DongBo | Hình 2.6 | `data_pipeline/dong_bo_hang_ngay.py` |
| 07_HoatDong_CanhBao | Hình 2.7 | `services/canh_bao_service.py` |
| 08_HoatDong_HuanLuyen | Hình 2.8 | `ml/du_bao_da_chat.py`, `ml/train_model.py` |

## 1. Mở tệp
1. Vào https://app.diagrams.net, hoặc cài bản draw.io Desktop.
2. Chọn **File → Open from → Device** rồi chọn tệp `.drawio`.

## 2. Sửa
- **Sửa chữ:** bấm đúp vào hình. Xuống dòng bằng Shift + Enter.
- **Di chuyển:** kéo hình; đường nối gắn với hình sẽ đi theo. Đường bị lệch thì chọn đường đó, kéo các điểm gấp màu xanh lá để chỉnh.
- **Thêm hình:** kéo từ thư viện bên trái.
  - Nhóm **UML**: Actor, Use Case (hình elip), Frame (khung alt/opt), Lifeline.
  - Nhóm **Entity Relation**: bảng ERD.
  - Nhóm **General**: hình chữ nhật bo góc (hoạt động), hình thoi (rẽ nhánh).
- **Nối hai hình:** rê chuột lên hình nguồn, kéo mũi tên xanh sang hình đích. Muốn đổi kiểu mũi tên thì mở bảng **Format → Arrow** bên phải.
  - **Use-case:** kế thừa giữa các tác nhân dùng tam giác rỗng (Block, bỏ chọn Fill); «include» dùng nét đứt với mũi tên Open.
  - **ERD:** đầu 1 chọn **ERmandOne**, đầu n chọn **ERmany**.
  - **Tuần tự:** thông điệp gọi dùng nét liền với mũi tên đặc; thông điệp trả về dùng nét đứt với mũi tên Open.
- **Giữ kiểu đen trắng:** trong Format chọn Fill màu trắng, Line màu đen, Font Arial cỡ 10–12. Không tô màu.

## 3. Xuất ảnh để dán vào Word/WPS
1. Chọn **File → Export as → PNG**.
2. Đặt Zoom 200%, Border width 10, bỏ chọn Transparent Background, rồi bấm **Export**.
3. Trong WPS:
   - Bấm chuột phải vào hình cũ, chọn **Thay đổi ảnh** (Change Picture) để giữ nguyên vị trí và chú thích.
   - Đặt chiều rộng ảnh khoảng 16 cm cho vừa lề trang, rồi giữ nguyên chú thích "Hình 2.x" và dòng "Nguồn: ..." bên dưới.

## 4. Khi CSDL thay đổi
- Thêm hoặc xóa bảng, cột thì sửa ERD: bấm đúp vào bảng và sửa từng dòng.
- Dòng có `PK` là khóa chính, `FK` là khóa ngoại, `UQ` là ràng buộc duy nhất.
- Đối chiếu bằng câu lệnh sau, chạy trong pgAdmin:

```sql
SELECT table_name, column_name, udt_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name <> 'spatial_ref_sys' ORDER BY table_name, ordinal_position;
```
