# Runs once before Grafana starts: reads Grafana's secrets out of Vault,
# writes them where Grafana expects files rather than environment
# variables, and syncs the read-only database login to match.
#
# Built on the Postgres image because it already carries psql; curl and
# jq are for Vault's HTTP API, which avoids pulling in the Vault CLI for
# one request.
FROM postgres:16-alpine

RUN apk add --no-cache curl jq

COPY ./bootstrap.sh /usr/local/bin/bootstrap.sh
RUN chmod +x /usr/local/bin/bootstrap.sh

ENTRYPOINT ["/usr/local/bin/bootstrap.sh"]
