# Intentionally empty.
#
# This dashboard reads deployment state live from the Kubernetes API on every
# request, so it does not need to persist anything in a database. All "data"
# you see in the UI comes from `deployments.k8s_client` calling the K8s API.
#
# A previous version of this app used a sync worker that copied K8s state into
# Postgres. That was dropped in favor of live reads after instructor feedback:
# the result is simpler code, fewer moving parts, and a more real-time view.
