#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status

echo "Running Postgres init script..."

if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
    echo "Multiple database creation requested: $POSTGRES_MULTIPLE_DATABASES"

    for db in $(echo "$POSTGRES_MULTIPLE_DATABASES" | tr ',' ' '); do
        echo "Checking database: $db"

        if psql -U "$POSTGRES_USER" -lqt | cut -d \| -f 1 | grep -qw "$db"; then
            echo "Database $db already exists, skipping."
        else
            echo "Database $db does not exist. Creating..."
            createdb -U "$POSTGRES_USER" "$db"
            echo "Database $db created successfully."
        fi
        psql -U "$POSTGRES_USER" -c "GRANT ALL PRIVILEGES ON DATABASE \"$db\" TO \"$POSTGRES_USER\";"
    done

    echo "All databases ensured."
fi

# A login Grafana can use to read -- and only read -- the platform's own
# data, so a dashboard can answer "how many videos were uploaded this week"
# from the database instead of from a metric nobody ever wrote. Created
# here so a fresh volume comes up complete; on an existing database the
# same statements are applied by hand once (see monitoring/README.md).
if [ -n "$GRAFANA_DB_PASSWORD" ]; then
    for db in $(echo "$POSTGRES_MULTIPLE_DATABASES" | tr ',' ' '); do
        echo "Granting read-only access on $db to grafana_ro..."
        psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" <<-SQL
            DO \$\$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                    CREATE ROLE grafana_ro LOGIN PASSWORD '$GRAFANA_DB_PASSWORD';
                END IF;
            END
            \$\$;
            GRANT CONNECT ON DATABASE "$db" TO grafana_ro;
            GRANT USAGE ON SCHEMA public TO grafana_ro;
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
            -- Tables a later migration adds must be readable too, without
            -- anyone remembering to come back here.
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
SQL
    done
fi
