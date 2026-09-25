# InsightHub Day 3 Terraform skeleton

[SPEC Day 3](SPEC.md) là contract của lượt triển khai. Root này pin Terraform `1.10.5` và provider trong `versions.tf`/`.terraform.lock.hcl`. Namespace và ServiceAccount có tên cố định `insighthub-prod` / `insighthub`. EKS, RDS PostgreSQL 16 và ElastiCache Redis 7 được khai báo trong `main.tf`; VPC và ít nhất hai private subnet là đầu vào của lab, không được tạo bởi root này. Ghi owner/lifecycle của chúng vào manifest trước khi apply. `db/init.sql` tạo schema và pgvector sau khi DB sẵn sàng; Terraform không tự chạy file SQL.

## Kiểm tra local, không tạo AWS resource

Chạy từ root repo trong WSL sau `source .venv/bin/activate`:

```sh
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false -input=false
terraform -chdir=infra validate
(cd infra && tflint --recursive)
checkov -d infra/
bash scripts/test-terraform-policy.sh
# Sau khi có plan thật từ đúng account/region, không commit tfplan hoặc tfplan.json:
# bash scripts/test-terraform-policy-plan.sh /secure/path/day3.tfplan
```

`init -backend=false` chỉ cài provider; có thể cần internet. `validate`, tflint và Checkov không chứng minh hạ tầng đã chạy. Review mọi cảnh báo; không sửa assertion hoặc thêm skip để làm scan xanh. `.terraform.lock.hcl` được commit, còn `.terraform/`, state, plan và tfvars chứa dữ liệu nhạy cảm không được commit.

Conftest `0.70.1` trong `.venv` kiểm tra Terraform plan JSON: tag bắt buộc, mã hóa RDS/Redis, RDS private/Multi-AZ, EKS private-only API, Redis hai node/automatic failover/Multi-AZ, secret rotation, giới hạn node/storage và chặn delete trong plan triển khai. `scripts/test-terraform-policy.sh` chạy fixture hợp lệ và fixture vi phạm; PASS với fixture chỉ chứng minh logic policy, không thay thế kiểm tra plan thật. Policy capacity không phải ước tính USD; dùng Infracost riêng. Plan JSON có thể chứa secret, nên lưu cục bộ an toàn và không commit.

Checkov `3.3.19` hiện có 164 checks đạt, 0 findings, 0 skipped; report ở `evidence/day3-checkov.txt`. Năm findings ban đầu đã được xử lý bằng EKS private-only, RDS Multi-AZ, Redis hai node với failover và Secrets Manager rotation có Lambda bốn bước. Không thêm skip. Kết quả scan chỉ chứng minh cấu hình tĩnh; chưa chứng minh rotation chạy được trên AWS.

## Điều kiện trước AWS

Xác nhận sandbox account/region/profile, VPC/private subnet/AZ, đường truy cập EKS private-only từ runner/mạng kết nối VPC, loại node/DB/cache và ước tính chi phí theo thời gian lab. Ghi `lab-manifest.json` như [guide chi phí](../docs/Guide_Local_AWS_Cost_DO2603.md), kể cả resource ID không hỗ trợ tag. Cấp `TF_VAR_redis_auth_token` bằng nguồn bảo mật tại thời điểm chạy; Terraform state/plan vẫn chứa token, nên phải bảo vệ state bucket và mọi bản plan. RDS tự quản lý master password trong Secrets Manager. Kiểm tra cách cấp DB user riêng cho ứng dụng trước khi Helm deploy; không dùng master user làm tài khoản ứng dụng.

Rotation Lambda chạy trong private subnets, gọi Secrets Manager và ElastiCache API qua hai interface VPC endpoints rồi xác thực token mới trực tiếp với Redis qua TLS. Mỗi lượt dùng bốn bước `createSecret → setSecret → testSecret → finishSecret`; `setSecret` gọi `ROTATE`, để token cũ còn hiệu lực trong thời gian chuyển tiếp. Tạo AWS Signer profile cùng S3 bucket versioned/encrypted cho artifact **trước** lượt plan/apply, ký đúng `infra/rotation/handler.py` thành ZIP có `handler.py` ở root, rồi cung cấp `rotation_signing_profile_version_arn` và ba biến `rotation_signed_s3_*`. Lambda enforce code signing; ZIP chưa ký hoặc ký sai profile sẽ không deploy. Việc upload/ký là cloud mutation, cần review riêng khi thực hiện. Không trỏ Lambda vào ZIP chưa ký chỉ để đạt scanner.

Trước apply cần rà soát Infracost cho một RDS standby, Redis replica thứ hai, hai interface endpoints theo số AZ, Lambda/Signer/SQS/X-Ray và đường truy cập EKS private. Sau rotation phải cập nhật Kubernetes runtime Secret từ AWSCURRENT và rollout API/worker trước lượt rotation kế tiếp; Helm hiện chỉ tham chiếu một external Secret và chưa tự đồng bộ giá trị mới. Không kết luận rotation vận hành PASS trước khi kiểm chứng đường đồng bộ, thử rotation và plan lại sau rotation để chắc Terraform không đặt token cũ trở lại.

Khi có AWS inputs thật, tạo plan giai đoạn một với `manage_namespace=false` và không chạy apply. Kiểm tra `aws sts get-caller-identity` khớp `aws_account_id`, khởi tạo backend S3, chạy `terraform -chdir=infra plan -input=false -out=/secure/path/day3.tfplan`, rồi `bash scripts/test-terraform-policy-plan.sh /secure/path/day3.tfplan`. Script xuất plan JSON ra file tạm quyền hạn chế, chạy Conftest và xóa JSON khi kết thúc. Không lưu raw plan/JSON vào repo; chỉ lưu exit code, tóm tắt đã lược secret và hash trong evidence. Không gọi fixture là plan thật.

EKS control-plane logs, RDS monitoring/Performance Insights và customer-managed KMS key có thể phát sinh thêm phí; đưa chúng vào Infracost và budget trước apply. KMS key có thời gian chờ xóa tối thiểu 7 ngày trong cấu hình hiện tại; ghi trạng thái pending deletion và owner vào inventory teardown cho đến khi AWS xóa xong.

S3 state bucket phải tồn tại, bật encryption/versioning và có quyền đọc/ghi/xóa `.tflock`. `backend.tf` dùng `use_lockfile`; bucket/key/region được cung cấp khi `terraform init -backend=true` bằng tham số `-backend-config` của đúng lượt lab, không commit credential hoặc file cấu hình backend. Không dùng DynamoDB lock. Plan phải được review trên đúng account/region/workspace; không chạy apply khi có destroy bất ngờ hoặc ngoài manifest.

Namespace là giai đoạn hai: giữ `manage_namespace=false` khi tạo EKS; sau khi cluster và node group Ready, cấu hình kube authentication và đổi `manage_namespace=true` để Terraform tạo namespace cùng ServiceAccount/IRSA binding. Cả hai plan đều phải được review và có manual approval trước apply. Không dùng `-target` làm quy trình triển khai thường lệ.

## GitHub Actions Day 3

[`iac.yml`](../.github/workflows/iac.yml) chạy `fmt → lint/validate → Checkov → Conftest fixture → app build/test/image scan` trên PR và push vào `prod/main` hoặc nhánh `prod/day3-*`. Các job PR dùng GitHub-hosted runner; chúng không truy cập kind hoặc AWS. App job upload `deployment` (chart, manifest render và image IDs; không chứa image tar) cùng `verification-source/source-manifest.json` có hash source/artifact từ chính run; report scan có artifact riêng. Source binding không tự chứng minh deployment đã chạy.

Sau khi merge vào `prod/main`, job `deploy-kind` chạy trên runner `self-hosted, linux, insighthub-vpc`: kiểm tra kube context `kind-insighthub`, build/load ba image từ commit được merge, `helm upgrade --install` vào namespace `insighthub-prod`, chờ đủ năm workload và chạy smoke qua port-forward localhost. Job lưu `local-kind-evidence`; nó không tạo cluster mới, không xóa PVC hoặc uninstall release. Smoke thêm một tài liệu mẫu vào PostgreSQL local hiện có. Không cho PR chạy code trên self-hosted runner của repo public vì runner có Docker socket và kubeconfig. Runner phải Online và có ba nhãn trên; `kind`, Docker, kubectl và Python cần khả dụng từ cùng user runner. Custom label chỉ chọn runner, không cấp kết nối VPC.

Chỉ lượt `workflow_dispatch` từ `prod/main` mới chạy AWS `plan → Conftest trên plan thật → cost → apply`. Chọn `foundation` trước (`manage_namespace=false`); sau khi EKS/node group Ready và runner kết nối VPC thật đã được xác nhận, chọn `namespace` (`manage_namespace=true`). Namespace stage chạy trên self-hosted **Linux** runner để truy cập private EKS endpoint. Khi AWS sandbox hết hạn, không dispatch hai stage này; CI local không chứng minh EKS/RDS/ElastiCache, OIDC, HTTPS hoặc teardown.

Trước khi dispatch, cấu hình GitHub repository variables: `AWS_ACCOUNT_ID=154931139523`, `AWS_REGION=ap-southeast-1`, `VPC_ID=vpc-0a44e0c464a42d898`, `PRIVATE_SUBNET_IDS_JSON` là JSON array của hai subnet đã cho **sau khi xác nhận khác AZ và private**, `TF_STATE_BUCKET=do2603-ndlong`, `TF_STATE_KEY=insighthub-prod/terraform.tfstate`, `TERRAFORM_PLAN_ROLE_ARN`, `TERRAFORM_APPLY_ROLE_ARN`, `LAB_OWNER`, `COST_CENTER`, `LAB_ID`, `EXPIRES_AT`, `NODE_INSTANCE_TYPE`, `DB_INSTANCE_CLASS`, `CACHE_NODE_TYPE`, `ROTATION_SIGNED_S3_BUCKET`, `ROTATION_SIGNED_S3_KEY`, `ROTATION_SIGNED_S3_OBJECT_VERSION`, `ROTATION_SIGNING_PROFILE_VERSION_ARN`, `MAX_LAB_USD=25`. Mức 25 USD cho 4 giờ là ngưỡng lab tạm đề xuất, cần review lại với giá Infracost và thời gian thực tế trước apply. Repository secrets: `REDIS_AUTH_TOKEN` và `INFRACOST_API_KEY`. Không đưa token vào variables, tfvars, log hoặc evidence.

Tạo AWS IAM OIDC provider cho `token.actions.githubusercontent.com` với audience `sts.amazonaws.com` **ngoài** Terraform root này để tránh bootstrap vòng lặp. Plan role chỉ tin token `aud=sts.amazonaws.com`, `sub=repo:LongNgd/insighthub:ref:refs/heads/prod/main`; apply role chỉ tin `aud=sts.amazonaws.com`, `sub=repo:LongNgd/insighthub:environment:insighthub-prod`. Giới hạn plan role ở read/plan cần thiết, S3 state lock và prefix `insighthub-prod/ci-plans/`; apply role có quyền thay đổi resource theo manifest và đọc đúng plan object version. Cả hai role cần quyền S3 backend gồm state/lockfile; apply role cần `GetObjectVersion` cho plan. Không cấp access key dài hạn. Tạo GitHub Environment `insighthub-prod` với **required reviewer** là tài khoản của bạn, giới hạn deployment branch `prod/main`; nếu tự duyệt, tắt `Prevent self-review`. YAML `environment:` chỉ trỏ tới Environment: quy tắc reviewer phải bật trong GitHub Settings trước khi chạy, nếu không sẽ không có manual approval thực sự.

Kiểm tra bucket state/versioned plan thuộc đúng account/region, đã bật versioning, default encryption và quyền lockfile; workflow sẽ fail ở preflight nếu thiếu versioning/encryption. Bật S3 Block Public Access, policy giới hạn role, và lifecycle ngắn cho `insighthub-prod/ci-plans/`. Plan nhị phân chứa giá trị nhạy cảm, vì vậy workflow không upload plan/JSON làm GitHub artifact: plan role ghi vào S3, apply tải đúng `VersionId` và kiểm tra SHA-256 sau khi Environment được duyệt. Evidence an toàn gồm URL run/job, commit SHA, stage, kết quả gate, plan hash/object version, bản tóm tắt Infracost và quyết định duyệt; không lưu raw plan hoặc secret. Cost job dùng HCL và placeholder Redis chỉ để định giá, không gửi plan JSON có secret tới Infracost; ước tính chi phí chưa gồm mọi usage/tax, nên reviewer vẫn phải xem breakdown và manifest trước khi duyệt.

Hiện chưa xác minh AWS CLI login, bucket, OIDC roles, signed Lambda artifact, GitHub Environment hoặc runner VPC. Vì thế có thể kết luận riêng gate tĩnh, app CI và kind smoke sau khi chúng chạy; không ghi `plan/cost/apply PASS` trước khi các điều kiện AWS có thật. Sau khi tạo roles/secret/variables, chạy workflow từ `prod/main`, xem kết quả `foundation`, duyệt apply, xác nhận EKS Ready rồi lặp lại stage `namespace` trên runner VPC. Lưu link run và evidence theo `scripts/VERIFICATION_CONTRACT.md`.

## Giới hạn skeleton và teardown

Helm local đã có; workflow GitHub Actions/OIDC và Infracost đã được khai báo nhưng chưa có run AWS xanh. HTTPS, smoke AWS và evidence CI chưa được triển khai; Conftest hiện mới được kiểm tra trên fixture, chưa trên AWS plan thật. RDS extension `vector` phải được bật bằng DB role phù hợp trước khi chạy ứng dụng. ElastiCache bật TLS và AUTH; ứng dụng cần cấu hình kết nối Redis tương thích trong bước Helm. Kiểm chứng riêng namespace, IAM trust, DB/cache private/encrypted/tagged và ba workload Ready.

Sau lượt lab, xóa resource con do Kubernetes controller tạo trước. Để teardown RDS, review plan riêng chuyển `rds_deletion_protection=false`, phê duyệt và apply thay đổi đó trước destroy; Conftest sẽ chặn plan này theo chủ đích nên ghi ngoại lệ teardown cùng người duyệt và evidence, không bỏ policy khỏi gate triển khai. Sau đó review destroy plan, apply chính plan đó rồi đối chiếu inventory AWS read-only ở mọi region đã dùng. `terraform state list` rỗng không đủ chứng minh không còn orphan, snapshot hoặc tài nguyên tính phí. Không giữ EKS/RDS/Redis qua đêm để duy trì URL demo.
