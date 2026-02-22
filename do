#!/usr/bin/env bash

set -eu

usage() {
    echo "Usage:"
    echo
    echo "  do deploy         # deploy the monorepo"
    echo "  do env-sync       # install python dependencies"
    echo "  do machine-setup  # one-time machine set-up"
    echo "  do repo-setup     # one-time repo set-up"
    echo "  do test           # run project tests"
    echo "  do test-accept    # run project tests and accept expecttest output"
    # tests-for-files intentionally not documented
    echo
}

do_deploy() {
    logdir="$HOME/.ian/logs/deploy"
    mkdir -p "$logdir"
    # slightly annoying: '%z' prints '0500' but log files produced by Python have it as
    # '05:00'; GNU date supports '%:z' to do this but macOS date does not.
    logfile="$logdir/$(date "+%Y-%m-%dT%H:%M:%S.%N%z").log"
    .venv/bin/python3 deploy.py "$@" 2>&1 | tee -a "$logfile"
}

do_env_sync() {
    no_args "$@"

    echo "*** syncing python dependencies"
    sync_python_deps
}

sync_python_deps() {
    (
        source .venv/bin/activate
        uv pip compile requirements.in -o requirements.txt
        uv pip sync requirements.txt
    )
}

do_repo_setup() {
    no_args "$@"
    make_venvs
    sync_python_deps
}

# TODO(2025-05): replace this with `kg remote-setup` command
do_machine_setup() {
    no_args "$@"

    kgdir="$HOME/.ian"
    remote_repo="$kgdir/repos/master"
    if [[ -e "$remote_repo" ]]; then
        echo "aborting: remote repo already exists ($remote_repo)"
        exit 1
    fi

    make_venvs
    do_env_sync

    mkdir -p "$remote_repo"
    git init "$remote_repo"
    # By default, Git will not let you push to a non-bare repo.
    # This option allows pushes but only if they will not overwrite local modifications.
    #
    # https://stackoverflow.com/questions/804545/
    git -C "$remote_repo" config receive.denyCurrentBranch updateInstead

    git remote add local "$remote_repo"
    git push -u local master

    mkdir -p "$kgdir/apps/jobserver"

    (
        cd "$remote_repo"
        do_repo_setup
    )
}

make_venvs() {
    python3 -m venv .venv
}

do_test() {
    if [[ $# -eq 0 ]] || [[ "$1" == -* ]]; then
        .venv/bin/python3 -m unittest discover "$@"
    else
        args=()

        for x in "$@"; do
            if [[ "$x" == -* ]]; then
                break
            else
                args+=("$x")
                shift
            fi
        done

        for x in "${args[@]}"; do
            did=0
            if [[ -e "app/$x" ]]; then
                if [[ -e "app/$x/tests.py" ]] || [[ -e "app/$x/tests/" ]]; then
                    echo "*** testing app/$x"
                    .venv/bin/python3 -m unittest "app/$x/tests.py" "$@"
                else
                    echo "*** skipping app/$x, no tests found"
                fi
                did=1
            fi

            if [[ -e "lib/$x" ]]; then
                if [[ -e "lib/$x/tests.py" ]] || [[ -e "lib/$x/tests/" ]]; then
                    echo "*** testing lib/$x"
                    .venv/bin/python3 -m unittest "lib/$x/tests.py" "$@"
                else
                    echo "*** skipping lib/$x, no tests found"
                fi
                did=1
            fi

            if [[ "$did" = "0" ]]; then
                echo "error: $x is not in app/ or lib/"
                exit 1
            fi
        done
    fi
}

do_tests_for_files() {
    (
        for f in "$@"; do
            if [[ "$f" == "lib/"* ]] || [[ "$f" == "app/"* ]]; then
                echo "$f"
            fi
        done
    ) | cut -d/ -f2 | sort | uniq | xargs -r ./do test
    # `cut -d/ -f2` extracts the second part of the path, i.e. the lib/app name
    # `xargs -r` runs the command only if the argument list is non-empty
}

no_args() {
    if [[ $# -gt 0 ]]; then
        usage
        exit 1
    fi
}

main() {
    cd "$(dirname "$(realpath "$0")")"

    subcmd="$1"
    shift
    case "$subcmd" in
        # NOTICE: If you add a command here, don't forget to also add it to `usage()`.
        deploy)
            do_deploy "$@"
            ;;
        env-sync)
            do_env_sync "$@"
            ;;
        machine-setup)
            do_machine_setup "$@"
            ;;
        repo-setup)
            do_repo_setup "$@"
            ;;
        test)
            do_test "$@"
            ;;
        test-accept)
            export EXPECTTEST_ACCEPT=1
            do_test "$@"
            ;;
        tests-for-files)
            do_tests_for_files "$@"
            ;;
        *)
            usage
            exit 1
        ;;
    esac
}

main "$@"
