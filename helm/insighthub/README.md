# InsightHub Helm chart

Local kind chạy năm thành phần trong namespace `insighthub-prod`: `web`, `api`, `worker`, PostgreSQL/pgvector và Redis. Chart không tạo Namespace vì namespace local đã do `kubernetes/mcp/mcp-readonly.yaml` tạo; trên EKS namespace và ServiceAccount ứng dụng do Terraform quản lý. Dùng kubeconfig admin của kind cho deploy, không dùng kubeconfig `mcp-readonly`.

## Triển khai local

Chạy từ repo root trong WSL sau `source .venv/bin/activate`. Kiểm tra `kubectl config current-context` là `kind-insighthub` trước các lệnh mutation.

```sh
diff -u <(tr -d '\r' < infra/db/init.sql) helm/insighthub/files/init.sql
helm lint helm/insighthub -f helm/insighthub/values-local.yaml
helm template insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml > /tmp/insighthub-rendered.yaml

python scripts/create-local-k8s-secret.py
IMAGE_TAG=$(git rev-parse --short=12 HEAD)
docker build -t "insighthub-api:$IMAGE_TAG" ./api
docker build -t "insighthub-worker:$IMAGE_TAG" -f ingestion-worker/Dockerfile .
docker build -t "insighthub-web:$IMAGE_TAG" ./web
kind load docker-image --name insighthub "insighthub-api:$IMAGE_TAG" "insighthub-worker:$IMAGE_TAG" "insighthub-web:$IMAGE_TAG"
helm upgrade --install insighthub helm/insighthub -n insighthub-prod -f helm/insighthub/values-local.yaml --set-string "images.api.tag=$IMAGE_TAG" --set-string "images.worker.tag=$IMAGE_TAG" --set-string "images.web.tag=$IMAGE_TAG" --wait --timeout 8m
```

`create-local-k8s-secret.py` tạo mật khẩu ngẫu nhiên và Secret qua stdin của `kubectl create`; không in giá trị hoặc lưu vào chart/Git. Script không xoay mật khẩu khi Secret đã tồn tại và từ chối tạo mới nếu PVC PostgreSQL cũ còn đó. Không dùng `helm --set` cho credential. Redis dùng AUTH/AOF; PostgreSQL dùng Secret và chỉ chạy `files/init.sql` khi PVC mới. Khi `infra/db/init.sql` thay đổi, đồng bộ `files/init.sql` ở định dạng LF và review diff; không tự xóa PVC để chạy lại init.

## Kiểm tra runtime

```sh
kubectl get pods,deploy,sts,svc,pvc -n insighthub-prod
kubectl rollout status deployment/insighthub-api -n insighthub-prod
kubectl rollout status deployment/insighthub-worker -n insighthub-prod
kubectl rollout status deployment/insighthub-web -n insighthub-prod
kubectl rollout status statefulset/insighthub-postgres -n insighthub-prod
kubectl rollout status statefulset/insighthub-redis -n insighthub-prod
helm status insighthub -n insighthub-prod
kubectl logs deployment/insighthub-api -n insighthub-prod --tail=100
kubectl logs deployment/insighthub-worker -n insighthub-prod --tail=100
```

Ở hai terminal riêng, chạy `kubectl port-forward -n insighthub-prod svc/insighthub-api 18000:8000 --address 127.0.0.1` và `kubectl port-forward -n insighthub-prod svc/insighthub-web 13000:3000 --address 127.0.0.1`. Dùng cổng khác Compose để có thể kiểm tra hai môi trường cùng lúc. Sau đó chạy `python scripts/smoke-k8s-local.py --api-url http://127.0.0.1:18000 --web-url http://127.0.0.1:13000 --poll-timeout 30`. Smoke yêu cầu `/healthz`, `/readyz`, web health trả 200; upload trả đúng 202 trong ≤1 giây; poll đúng ID tới `ready` và `chunk_count>0` trong ≤30 giây; `/chat` trả 200 có answer/sources/contexts; `/metrics` có sample số hữu hạn. Đây là fixture pipeline local, chưa chứng minh provider thật hoặc HTTPS/EKS.

## Chuyển sang EKS

`values-eks.yaml` tắt PostgreSQL và Redis trong chart, dùng RDS/ElastiCache qua `DATABASE_URL`/`REDIS_URL` ở Secret ngoài chart, và tham chiếu ServiceAccount `insighthub` do Terraform/IRSA tạo. Cần cấu hình image registry/digest, provider thật, TLS và cơ chế đồng bộ Secret từ Secrets Manager trước khi deploy. HTTPS ingress và smoke trên URL thật nằm ở bước AWS riêng. Không đưa credential vào values, log hoặc evidence.

`helm uninstall` sẽ xóa PVC do chart tạo; chỉ thực hiện sau khi đã review dữ liệu và backup cần giữ. Không dùng thao tác xóa để làm test xanh.
