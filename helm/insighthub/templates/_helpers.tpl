{{- define "insighthub.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "insighthub.fullname" -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "insighthub.labels" -}}
app.kubernetes.io/name: {{ include "insighthub.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "insighthub.selectorLabels" -}}
app.kubernetes.io/name: {{ include "insighthub.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "insighthub.image" -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
