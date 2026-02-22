#!/usr/bin/env bash

set -eu

psql_count() {
   psql -c '\t on \a off' -c 'select count(*) from bookmarks;' -d testdb --no-align
}

main() {
    ./lcl db schema test

    echo "==> importing bookmarks"
    ./lcl bookmarks import chrome
    echo "count: $(psql_count)"

    echo
    echo "==> deleting one bookmark"
    psql -c 'delete from bookmarks where bookmark_id = (select max(bookmark_id) from bookmarks)' -d testdb
    echo "^ SHOULD be one less"
    echo "count: $(psql_count)"

    echo
    echo "==> importing bookmarks again"
    ./lcl bookmarks import chrome
    echo "count: $(psql_count)"
    echo "^ SHOULD be same as original count"

    # recreating the database ensures that `bookmark_id` starts from 1 again
    ./lcl db schema test
    ./lcl bookmarks import test

    echo
    echo "==> starting server"
    port="5454"
    ./lcl bookmarks serve -port "$port" &>/dev/null &
    server_pid=$!
    sleep 1
    base_url="http://127.0.0.1:$port"

    path="/api/load"
    echo
    echo "==> hitting $path"
    curl -X GET "$base_url$path"

    path="/api/archive"
    echo
    echo "==> hitting $path"
    curl -X POST -H "Content-Type: application/json" -d '{"bookmark_id": 1, "reason": "read"}' "$base_url$path"

    path="/api/unarchive"
    echo
    echo "==> hitting $path"
    curl -X POST -H "Content-Type: application/json" -d '{"bookmark_id": 1, "reason": "read"}' "$base_url$path"

    path="/api/update"
    echo
    echo "==> hitting $path"
    curl -X POST -H "Content-Type: application/json" -d '{"appeal":"","bookmark_id":2,"reading_time":"","reason_archived":"","source":"test","source_id":"","tags":["a", "b", "c"],"time_archived":null,"time_created":"2025-08-06T00:01:42.465781-04:00","title":"New title","url":"https://example.com/new-url"}' "$base_url$path"
    kill "$server_pid"

    # clean up the database
    ./lcl db schema test
}

main "$@"
