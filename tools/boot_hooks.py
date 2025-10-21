# Käynnistyy sivuvaikutuksena importissa
from .version_stamp import VERSION, log_startup
from . import ops_runtime

# healthz + heartbeat + metrics päälle
ops_runtime.start_healthz_server()
ops_runtime.start_heartbeat()
ops_runtime.start_metrics_server()

# versioleima käynnistyslogiin
log_startup(__name__)
