# Monitoring

Everything Grafana shows is defined by the files in this folder. Nothing
is configured by clicking: a dashboard built in the browser lives in one
Docker volume on one machine, which is exactly how this project lost the
only dashboard it had.

```
monitoring/
├── prometheus.yaml      what Prometheus scrapes
├── datasources.yaml     Prometheus, Loki and the platform database
├── dashboards.yaml      tells Grafana where the dashboards are
├── dashboards/          the dashboards themselves, one file each
├── alerting.yaml        alert rules
├── loki-config.yaml     log storage
└── promtail-config.yaml ships container logs into Loki
```

## Getting in

`http://localhost/grafana`, user `admin`. The password is in Vault:

```bash
docker exec vault vault kv get -field=ADMIN_PASSWORD secret/grafana
```

It is the container's own admin account — not anybody's personal login.
The route exists **only in the dev profile**
(`docker-compose.dev.yml`); the production layout does not publish
Grafana at all.

### How the secret gets there

Grafana cannot read Vault itself; that is an Enterprise feature. So
`grafana-bootstrap` runs first, reads `secret/grafana`, and writes the
values as mode-400 files owned by Grafana's uid. Grafana reads them with
`GF_SECURITY_ADMIN_PASSWORD__FILE` and, in `datasources.yaml`,
`$__file{...}`.

Files rather than environment variables on purpose: an environment
variable is visible to anything that can run `docker inspect` or read
`/proc`, and it shows up in `docker compose config`.

One wrinkle worth knowing: Grafana applies the admin password **only
when it first creates the user**, on an empty volume. An installation
that was ever created with `admin`/`admin` keeps it forever, whatever
the configuration says. `Docker/grafana/entrypoint.sh` therefore resets
it from the file on every start, before the server comes up.

The read-only database login is kept in step by the same bootstrap: it
runs `CREATE`/`ALTER ROLE` with the password from Vault on every start,
so an existing database is corrected rather than left for somebody to
fix by hand.

To change the password:

```bash
docker exec vault vault kv patch secret/grafana ADMIN_PASSWORD='<new>'
docker compose up -d --force-recreate grafana-bootstrap grafana
```

## The dashboards

| Dashboard | Answers |
|---|---|
| **API — FastAPI** | Is the API serving requests, how fast, how many fail, and which routes. Includes the gateway, so media served straight from MinIO is counted too, and the application log. |
| **Transcoding** | Is encoding keeping up with uploads. Queue backlog, outcomes, duration, GPU vs CPU, worker resources, converter log. |
| **Infrastructure** | Postgres, Redis, Elasticsearch, MinIO, RabbitMQ and per-container CPU, memory and network. |
| **Platform** | The product rather than the machines: uploads, signups, views, unique viewers, watch time, where views come from, what is stuck in the pipeline. Read straight from the database. |

## Where the numbers come from

Three sources, and the difference matters:

**Prometheus** — numbers the services count about themselves, scraped
every 15 seconds. Two kinds:

- *written by us*: `fastapi_*` from `backend/src/services/metrics.py`,
  `convertor_*` from `services/convertor/src/metrics.py`,
  `video_search_requests_total` from the search route;
- *collected by exporters*: Postgres, Redis and Elasticsearch speak no
  Prometheus of their own, so a small translator sits beside each one.
  RabbitMQ and MinIO have the endpoint built in; cAdvisor reports every
  container at once.

**Loki** — the containers' log output, shipped by Promtail.

**The platform database** — Grafana reads `VideoDB` directly as a
datasource, through a login called `grafana_ro` that holds `SELECT` and
nothing else. This is what lets the Platform dashboard answer "how many
videos were uploaded this week" without anyone having to invent a metric
for every question somebody might ask.

### The read-only database login

`grafana_ro` holds `SELECT` and nothing else. It is created and kept in
step by `grafana-bootstrap` from `DB_PASSWORD` in `secret/grafana`,
on every start — there is no manual step and no second copy of the
password anywhere.

Worth confirming it really is read-only after any change:

```bash
PGPASSWORD=... psql -U grafana_ro -d VideoDB -h 127.0.0.1 -c "delete from videos where false;"
# ERROR:  permission denied for table videos
```

## Changing a dashboard

Provisioned dashboards are read-only in the UI on purpose
(`allowUiUpdates: false`): the file in git is the dashboard.

The workflow that actually works:

1. build and tune the query in **Explore** — immediate feedback, nothing
   to save;
2. edit the JSON in `dashboards/` and commit it;
3. Grafana reloads the folder every 30 seconds, so just wait, or
   `docker compose restart grafana`.

A new dashboard is a new file in `dashboards/`. Nothing else to register.

If you do build one in the UI, export it with **"Export for sharing
externally" OFF**. The "on" version wraps the file in `__inputs` and
`${DS_PROMETHEUS}` placeholders that only the import wizard expands —
provisioned as-is it loads, and every panel points at nothing.

## Alerts

Seven rules in `alerting.yaml`, all about things a person would notice:
a service that stopped reporting, 5xx responses, an encoding queue that
is not draining, failed encodes, object storage filling up, Postgres
connections climbing, Redis evicting data.

Each one has to stay true for minutes before it fires. That is not
decoration — an alert that fires on a ten-second spike gets muted within
a week, and then it protects nothing.

They are visible under **Alerting → Alert rules**.

### Delivery to Telegram — built, tested, switched off

**Status: implemented and working; not enabled, because no credentials
are stored yet.** Alerts currently fire into Grafana and go nowhere.

Nothing has to be built to turn it on — only two values have to exist
in Vault. The path itself was verified end to end with a throwaway
token: `grafana-bootstrap` generated the contact point and the
notification policy, Grafana loaded both, the token came back from the
API as `[REDACTED]` rather than in clear, every alert routed to
`telegram`, and clearing the credentials removed the contact point
again.

Put the bot token and the chat id in Vault and the contact point
appears; clear them and it disappears:

```bash
docker exec vault vault kv patch secret/grafana     TELEGRAM_BOT_TOKEN='123456:AA...' TELEGRAM_CHAT_ID='-1001234567890'
docker compose up -d --force-recreate grafana-bootstrap grafana
```

`grafana-bootstrap` writes `telegram.yaml` into the alerting
provisioning folder — a contact point plus a notification policy that
routes every alert to it. The file is generated rather than committed
because it carries the token; the rules beside it are committed because
they do not.

The policy groups by alert name, waits 30 seconds before the first
message and repeats at most every four hours. A channel that repeats
itself every thirty seconds gets muted, and a muted channel is worth
nothing.

Getting the two values: create the bot with
[@BotFather](https://t.me/BotFather) (`/newbot`) — it replies with the
token. For the chat id, send the bot a message (or add it to a group and
send one there), then read:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | grep -o '"chat":{"id":[-0-9]*'
```

A personal chat id is positive; a group's is negative and usually starts
`-100`. In a group the bot must be a member, and if the group has
privacy mode on it still receives what is sent to it directly.

## Adding a metric

In the application, declare it once and increment it where the thing
happens. One rule to remember, which this project learned the hard way:

**name the label values up front.** A labelled counter does not exist in
Prometheus until something increments it, so before the first failure
the panel asking for failures reads "no data" — which looks exactly like
a dead scrape. See `EncodeMetrics.__init__` and the `category="none"`
line in `backend/src/schemas/metric.py`.

And keep the labels low-cardinality. `get_route_path()` in the backend
records `/api/videos/{video_id}`, never the actual id; a label carrying
user or video ids would create a series per row and take Prometheus down.

## Checking it works

```bash
# every scrape target healthy
docker compose exec -T prometheus wget -qO- \
  "http://localhost:9090/api/v1/targets?state=active"

# dashboards Grafana actually loaded
curl -s -u admin:admin "http://localhost/grafana/api/search?type=dash-db"

# alert rules and their state
curl -s -u admin:admin \
  "http://localhost/grafana/api/prometheus/grafana/api/v1/rules"
```

A target that is `down`, or a dashboard missing from that list, means
some part of this is measuring nothing — and a panel with no data looks
the same as a service with no problems.
