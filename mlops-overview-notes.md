# Day 4 — MLOps architecture overview

**Phạm vi:** Đây là ghi chú kiến trúc cho trường hợp InsightHub sau này phục vụ
model do đội ML tự huấn luyện. InsightHub hiện dùng fixture hoặc provider được
cấu hình; tài liệu này không khẳng định dự án đã có model registry, pipeline
retrain hay một model nội bộ đang chạy. MLOps quản lý vòng đời *model* cùng dữ
liệu và kết quả đánh giá của nó; observability Day 4 hiện tại đo sức khỏe ứng
dụng và giúp điều tra incident.

## 1. Registry — quản lý model artifact và nguồn gốc

Registry lưu một version model bất biến cùng digest, version dữ liệu/feature,
code và tham số train, kết quả đánh giá, schema input/output và trạng thái
phê duyệt. Deployment tham chiếu một version/digest cụ thể; không lấy nhãn
`latest` làm căn cứ tái hiện hoặc rollback. Registry không phải nơi đưa raw
tài liệu người dùng hay credential vào artifact hoặc metadata.

| Chiều so sánh | App artifact | Model artifact |
| --- | --- | --- |
| Nội dung | Code, image và cấu hình chạy service | Weights/tokenizer hoặc bộ xử lý tương đương, schema và metadata model |
| Nguồn gốc | Commit, dependency và build pipeline | Dữ liệu/feature version, code train, tham số và experiment |
| Tiêu chí chấp nhận | Tests, bảo mật, API contract, rollout health | Chất lượng, an toàn, tương thích dữ liệu, latency và chi phí serving |
| Cách quay lại | Rollback app image/config | Chọn lại model version đã duyệt; app có thể giữ nguyên |

**Ranh giới:** ML Engineer chịu trách nhiệm train, đánh giá và đăng ký model
candidate. DevOps/ML Platform vận hành registry, quyền truy cập, lưu trữ và
cơ chế pin artifact trong môi trường chạy; không tự nhận model đạt chất lượng.

## 2. Approval Gate — quyết định version nào được phục vụ

Luồng đề xuất: ML đăng ký candidate → tự động kiểm tra artifact/digest, schema,
chất lượng trên bộ đánh giá cố định, safety/privacy, latency và chi phí → người
có thẩm quyền xem kết quả và duyệt → DevOps triển khai staging/canary rồi
production. Mỗi quyết định phải gắn model version, kết quả đánh giá, người
duyệt, thời điểm và mục tiêu môi trường. Một pipeline xanh không tự thay cho
phê duyệt chất lượng model.

**Ranh giới:** ML lead chịu trách nhiệm tiêu chí và kết luận chất lượng; product
hoặc risk owner duyệt tác động sản phẩm khi cần. DevOps thực thi gate bằng CI,
RBAC và quy trình deploy, kiểm tra khả năng phục vụ và rollback. Quyền duyệt
phải được hệ thống thực thi, không chỉ ghi trong prompt của agent.

## 3. Drift — phát hiện thay đổi và điều tra đúng tầng

*Data drift* là phân phối input/feature thay đổi so với dữ liệu tham chiếu;
*concept drift* là quan hệ giữa input và kết quả đúng thay đổi, nên chất lượng
model có thể giảm dù phân phối input trông ổn. Data drift có thể đo từ thống
kê feature đã làm sạch; xác nhận concept drift thường cần nhãn/feedback đến
muộn và đánh giá của ML. Latency, lỗi HTTP, queue và pod restart chỉ nói về
sức khỏe serving, không tự chứng minh model drift.

Khi drift alert fire, DevOps kiểm tra chất lượng tín hiệu, version đang phục
vụ, thời điểm deploy, lỗi pipeline, tài nguyên và các SLI ứng dụng; lưu bằng
chứng có timestamp rồi chuyển ML điều tra dữ liệu và chất lượng. ML xác nhận
nguyên nhân, chạy evaluation và quyết định sửa dữ liệu, model hay retrain.
Không đưa raw input hoặc thông tin định danh vào metric label/log. **DevOps
không tự retrain model** chỉ vì một alert fire.

## 4. Rollback — phục hồi version đã biết tốt và phân định trách nhiệm

Khi model mới làm chất lượng hoặc serving xấu đi, dùng kết quả canary và gate
đã ghi để chọn model version trước đó đã được duyệt. DevOps đổi routing hoặc
tham chiếu version, kiểm tra digest, health/latency/error và khả năng tương
thích schema; ML xác nhận lại chất lượng đầu ra trên bộ đánh giá và dữ liệu
phù hợp. Ghi thời gian đổi version, người phê duyệt, bằng chứng trước/sau và
nguyên nhân. Nếu lỗi nằm ở dữ liệu đầu vào hay ứng dụng, quay lại model đơn
thuần có thể không giải quyết được sự cố.

| Giai đoạn | Chủ trách nhiệm chính | Vai trò phối hợp |
| --- | --- | --- |
| Train, evaluation, quyết định retrain | ML Engineer | DevOps cấp hạ tầng và telemetry |
| Đăng ký candidate, mô tả lineage | ML Engineer | DevOps vận hành registry/RBAC |
| Duyệt chất lượng và tác động sản phẩm | ML lead / product hoặc risk owner | DevOps thực thi approval gate và audit |
| Deploy, serving, health và rollback thao tác | DevOps / ML Platform | ML xác nhận model version và chất lượng |
| Điều tra drift | ML xác nhận ý nghĩa và hành động với model | DevOps xác minh tín hiệu, hạ tầng và timeline |

Đối với InsightHub hiện tại, ba incident Day 4 là **fault inject vào fixture**
và được xử lý bằng telemetry ứng dụng cùng RCA; chúng không phải bằng chứng
model drift hoặc lý do để train lại model.
