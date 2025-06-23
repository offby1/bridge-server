FROM grafana/grafana:latest
USER grafana
COPY dashboards/ /etc/grafana/dashboards/
COPY provisioning/ /etc/grafana/provisioning/

# I don't actually use grafana-llm-app, but if I don't install it, the profiles page shows a popup complaining about its absence.
RUN grafana cli plugins install grafana-llm-app
