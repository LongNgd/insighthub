# InsightHub Day 3 Terraform skeleton

[SPEC Day 3](SPEC.md) là contract của lượt triển khai. Root này pin Terraform `1.10.5` và provider trong `versions.tf`/`.terraform.lock.hcl`. Namespace và ServiceAccount có tên cố định `insighthub-prod` / `insighthub`. EKS, RDS PostgreSQL 16 và ElastiCache Redis 7 được khai báo trong `main.tf`; VPC và ít nhất hai private subnet là đầu vào của lab, không được tạo bởi root này. Ghi owner/lifecycle của chúng vào manifest trước khi apply. `db/init.sql` tạo schema và pgvector sau khi DB sẵn sàng; Terraform không tự chạy file SQL.

## Kiểm tra local, không tạo AWS resource

Chạy từ root repo trong WSL sau `source .venv/bin/activate`:

```sh
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false -input=false
terraform -chdir=infra validate
cd infra && tflint --recursive
checkov -d infra/
```

`init -backend=false` chỉ cài provider; có thể cần internet. `validate`, tflint và Checkov không chứng minh hạ tầng đã chạy. Review mọi cảnh báo; không sửa assertion hoặc thêm skip để làm scan xanh. `.terraform.lock.hcl` được commit, còn `.terraform/`, state, plan và tfvars chứa dữ liệu nhạy cảm không được commit.

Checkov `3.3.19` hiện báo 6 finding: `CKV_AWS_38`, `CKV_AWS_39` (EKS public API), `CKV_AWS_293`, `CKV_AWS_157` (RDS deletion protection/Multi-AZ), `CKV2_AWS_50` (Redis failover) và `CKV2_AWS_57` (Redis secret rotation). Scan đầy đủ exit 1; chưa đạt gate Checkov. Public API bị giới hạn bởi `eks_api_cidrs` và validation cấm `0.0.0.0/0`, nhưng scanner không chứng minh được giá trị runtime của biến. Các finding còn lại cần quyết định theo budget, teardown và cơ chế xoay Redis token thực sự; không thêm skip hoặc cấu hình giả để lấy PASS.

## Điều kiện trước AWS

Xác nhận sandbox account/region/profile, VPC/private subnet/AZ, CIDR giới hạn cho EKS API, loại node/DB/cache và ước tính chi phí theo thời gian lab. Ghi `lab-manifest.json` như [guide chi phí](../docs/Guide_Local_AWS_Cost_DO2603.md), kể cả resource ID không hỗ trợ tag. Cấp `TF_VAR_redis_auth_token` bằng nguồn bảo mật tại thời điểm chạy; Terraform state/plan vẫn chứa token, nên phải bảo vệ state bucket và mọi bản plan. RDS tự quản lý master password trong Secrets Manager. Kiểm tra cách cấp DB user riêng cho ứng dụng trước khi Helm deploy; không dùng master user làm tài khoản ứng dụng.

EKS control-plane logs, RDS monitoring/Performance Insights và customer-managed KMS key có thể phát sinh thêm phí; đưa chúng vào Infracost và budget trước apply. KMS key có thời gian chờ xóa tối thiểu 7 ngày trong cấu hình hiện tại; ghi trạng thái pending deletion và owner vào inventory teardown cho đến khi AWS xóa xong.

S3 state bucket phải tồn tại, bật encryption/versioning và có quyền đọc/ghi/xóa `.tflock`. `backend.tf` dùng `use_lockfile`; bucket/key/region được cung cấp khi `terraform init -backend=true` bằng tham số `-backend-config` của đúng lượt lab, không commit credential hoặc file cấu hình backend. Không dùng DynamoDB lock. Plan phải được review trên đúng account/region/workspace; không chạy apply khi có destroy bất ngờ hoặc ngoài manifest.

Namespace là giai đoạn hai: giữ `manage_namespace=false` khi tạo EKS; sau khi cluster và node group Ready, cấu hình kube authentication và đổi `manage_namespace=true` để Terraform tạo namespace cùng ServiceAccount/IRSA binding. Cả hai plan đều phải được review và có manual approval trước apply. Không dùng `-target` làm quy trình triển khai thường lệ.

## Giới hạn skeleton và teardown

Helm, HTTPS, GitHub Actions/OIDC, Conftest, Infracost, smoke và evidence CI chưa được triển khai trong skeleton này. RDS extension `vector` phải được bật bằng DB role phù hợp trước khi chạy ứng dụng. ElastiCache bật TLS và AUTH; ứng dụng cần cấu hình kết nối Redis tương thích trong bước Helm. Kiểm chứng riêng namespace, IAM trust, DB/cache private/encrypted/tagged và ba workload Ready.

Sau lượt lab, xóa resource con do Kubernetes controller tạo trước, review destroy plan, apply chính plan đó rồi đối chiếu inventory AWS read-only ở mọi region đã dùng. `terraform state list` rỗng không đủ chứng minh không còn orphan, snapshot hoặc tài nguyên tính phí. Không giữ EKS/RDS/Redis qua đêm để duy trì URL demo.
