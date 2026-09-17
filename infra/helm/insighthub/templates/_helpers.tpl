{{- define "insighthub.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "insighthub.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "insighthub.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "insighthub.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "insighthub.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "insighthub.selectorLabels" -}}
app.kubernetes.io/name: {{ include "insighthub.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "insighthub.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "insighthub.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- required "serviceAccount.name is required when serviceAccount.create=false" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "insighthub.image" -}}
{{- $repository := required "image repository is required" .repository -}}
{{- $digest := required "immutable image digest is required" .digest -}}
{{- printf "%s@%s" $repository $digest -}}
{{- end }}

{{- define "insighthub.secretRenderer" -}}
- name: render-aws-secrets
  image: {{ include "insighthub.image" .Values.images.secretRenderer | quote }}
  imagePullPolicy: {{ .Values.images.secretRenderer.pullPolicy }}
  command: ["python", "-c"]
  args:
    - |
      import json
      import pathlib
      import shlex
      import urllib.parse

      rds = json.loads(pathlib.Path("/mnt/secrets/rds.json").read_text())
      redis = json.loads(pathlib.Path("/mnt/secrets/redis.json").read_text())
      db_user = str(rds["username"])
      db_password = str(rds["password"])
      db_host = str(rds["host"])
      db_port = str(rds.get("port", 5432))
      db_name = "insighthub"
      redis_password = urllib.parse.quote(str(redis["password"]), safe="")
      values = {
          "DATABASE_URL": "postgresql://{}:{}@{}:{}/{}?sslmode=require".format(
              urllib.parse.quote(db_user, safe=""),
              urllib.parse.quote(db_password, safe=""),
              db_host,
              db_port,
              db_name,
          ),
          "REDIS_URL": "rediss://:{}@{}:{}/0".format(
              redis_password,
              str(redis["host"]),
              str(redis.get("port", 6379)),
          ),
          "PGHOST": db_host,
          "PGPORT": db_port,
          "PGUSER": db_user,
          "PGPASSWORD": db_password,
          "PGDATABASE": db_name,
          "PGSSLMODE": "require",
      }
      target = pathlib.Path("/runtime/secrets.env")
      target.write_text("\n".join(
          "export {}={}".format(key, shlex.quote(value))
          for key, value in values.items()
      ) + "\n")
      target.chmod(0o400)
  securityContext:
{{ toYaml .Values.containerSecurityContext | indent 4 }}
  resources:
{{ toYaml .Values.resources.secretRenderer | indent 4 }}
  volumeMounts:
    - name: aws-secrets
      mountPath: /mnt/secrets
      readOnly: true
    - name: runtime-secrets
      mountPath: /runtime
{{- end }}

{{- define "insighthub.secretVolumes" -}}
- name: aws-secrets
  csi:
    driver: secrets-store.csi.k8s.io
    readOnly: true
    volumeAttributes:
      secretProviderClass: {{ include "insighthub.fullname" . }}-aws
- name: runtime-secrets
  emptyDir:
    medium: Memory
    sizeLimit: 1Mi
{{- end }}
