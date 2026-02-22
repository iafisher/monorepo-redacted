import aiohttp
import asyncio
import json
import shlex
import statistics
import subprocess
import time
import urllib.parse
from typing import Annotated, Awaitable

from iafisher_foundation.prelude import *
from iafisher_foundation.scripting import *
from lib import command, humanunits


SERVER = "iafisher.com"
REMOTE_DIR = "/var/fast-concordance/"


def shell2(*args: Any, **kwargs: Any) -> None:
    print("==> " + " ".join(map(str, args)))
    subprocess.run(args, check=True, **kwargs)


def rshell(remote_script: str) -> None:
    shell2("ssh", SERVER, f"bash -e -c {shlex.quote(remote_script)}")


def main_deploy(
    directory: Annotated[
        pathlib.Path,
        command.Extra(help="directory containing the fast-concordance files"),
    ],
    *,
    include_ebooks: Annotated[
        bool, command.Extra(help="deploy the (processed) ebook files")
    ],
    skip_build: Annotated[bool, command.Extra(help="skip building the server")],
) -> None:
    os.chdir(directory)

    merged_directory = directory / "merged"
    if not merged_directory.exists():
        bail(f"directory does not exist: {merged_directory}")

    public_directory = directory / "public"
    if not public_directory.exists():
        bail(f"directory does not exist: {public_directory}")

    binary_file = directory / "fast-concordance-linux"
    if skip_build:
        if not binary_file.exists():
            bail(f"file does not exist (and -skip-build was passed): {binary_file}")
    else:
        shell2(
            "env",
            "GOOS=linux",
            "GOARCH=amd64",
            "go",
            "build",
            "-o",
            binary_file,
            "cmd/server/main.go",
        )

    if include_ebooks:
        tar_gz_file = "merged.tar.gz"
        shell2(
            "tar",
            "--no-xattrs",
            "-czf",
            tar_gz_file,
            f"--directory={merged_directory}",
            ".",
        )
        shell2("scp", tar_gz_file, f"{SERVER}:{REMOTE_DIR}/{tar_gz_file}")

        deploy_ebooks_script = f"""\
cd {REMOTE_DIR}
mkdir merged.new
tar xf {tar_gz_file} --directory=merged.new
rm {tar_gz_file}
rm -rf merged
mv merged.new merged
"""

        rshell(deploy_ebooks_script)

    deploy_binary_script = f"""\
cd {REMOTE_DIR}
[[ -e fast-concordance ]] && mv fast-concordance fast-concordance.old
mv fast-concordance.new fast-concordance
"""

    shell2("scp", binary_file, f"{SERVER}:{REMOTE_DIR}/fast-concordance.new")
    rshell(deploy_binary_script)

    deploy_public_script = f"""\
cd {REMOTE_DIR}
[[ -e public.old ]] && rm -rf public.old
[[ -e public ]] && mv public public.old
mv public.new public
sudo chcon -R -t httpd_sys_content_t public
"""

    shell2("scp", "-r", public_directory, f"{SERVER}:{REMOTE_DIR}/public.new")
    rshell(deploy_public_script)

    mydir = pathlib.Path(__file__).resolve().parent
    systemd_file = mydir / "fast-concordance.service"
    shell2("scp", systemd_file, f"{SERVER}:{REMOTE_DIR}/{systemd_file.name}")
    deploy_systemd_script = f"""\
ln -sfn {REMOTE_DIR}/{systemd_file.name} ~/.config/systemd/user/{systemd_file.name}
systemctl --user daemon-reload
systemctl --user enable fast-concordance
systemctl --user restart fast-concordance
"""

    rshell(deploy_systemd_script)


def main_deploy_benchmark(
    directory: Annotated[
        pathlib.Path,
        command.Extra(help="directory containing the fast-concordance files"),
    ]
) -> None:
    os.chdir(directory)

    public_directory = directory / "public"
    if not public_directory.exists():
        bail(f"directory does not exist: {public_directory}")

    binary_file = directory / "benchmark-linux"
    shell2(
        "env",
        "GOOS=linux",
        "GOARCH=amd64",
        "go",
        "build",
        "-o",
        binary_file,
        "cmd/benchmark/main.go",
    )

    deploy_binary_script = f"""\
cd {REMOTE_DIR}
[[ -e benchmark ]] && mv benchmark benchmark.old
mv benchmark.new benchmark
"""

    shell2("scp", binary_file, f"{SERVER}:{REMOTE_DIR}/benchmark.new")
    rshell(deploy_binary_script)


def main_load_test(
    *,
    base_url: str = "https://iafisher.com",
    keyword: str = "vampire",
    n: Annotated[int, command.Extra(help="how many simultaneous requests to make")] = 1,
    trials: Annotated[int, command.Extra(help="repeat this many times")] = 1,
    gap: Annotated[
        Optional[datetime.timedelta],
        command.Extra(
            converter=humanunits.parse_duration, help="wait this long between requests"
        ),
    ] = None,
) -> None:
    asyncio.run(do_load_test(base_url, keyword=keyword, n=n, trials=trials, gap=gap))


async def do_load_test(
    base_url: str,
    *,
    keyword: str,
    n: int,
    trials: int,
    gap: Optional[datetime.timedelta],
) -> None:
    firsts: List[int] = []
    firsts_unqueued: List[int] = []
    lasts: List[int] = []
    durations: List[float] = []
    for trial_i in range(trials):
        async with aiohttp.ClientSession() as session:
            tasks: List[Awaitable[FetchResult]] = []
            delay_secs = 0.0
            for _ in range(n):
                tasks.append(
                    fetch_one(session, base_url, keyword=keyword, delay_secs=delay_secs)
                )
                if gap is not None:
                    delay_secs += gap.total_seconds()

            results = await asyncio.gather(*tasks)

            for result in results:
                firsts.append(result.ms_to_first_result)
                if result.ms_queued == 0:
                    firsts_unqueued.append(result.ms_to_first_result)
                lasts.append(result.ms_to_last_result)
                durations.append(result.ms_to_last_result - result.ms_to_first_result)
                print(
                    f"first:   {result.ms_to_first_result: >7,} ms"
                    + f"    last:   {result.ms_to_last_result: >7,} ms"
                    + f"    queued: {result.ms_queued: >7,} ms"
                    + f"    n: {result.num_results: >10,}"
                )

        if trial_i != trials - 1:
            time.sleep(2.0)
            print()

    if len(firsts) >= 2:
        print()
        first_mean = statistics.mean(firsts)
        first_stdev = statistics.stdev(firsts)
        print(f"first:             {first_mean: >7,.1f} ms (σ={first_stdev:.1f})")
        if firsts_unqueued:
            first_mean = statistics.mean(firsts_unqueued)
            first_stdev = statistics.stdev(firsts_unqueued)
            print(f"first (unqueued):  {first_mean: >7,.1f} ms (σ={first_stdev:.1f})")
        last_mean = statistics.mean(lasts)
        last_stdev = statistics.stdev(lasts)
        print(f"last:              {last_mean: >7,.1f} ms (σ={last_stdev:.1f})")
        print(f"max:               {max(firsts): >7,.1f} ms")
        duration_mean = statistics.mean(durations)
        duration_stdev = statistics.stdev(durations)
        print(f"duration:          {duration_mean: >7,.1f} ms (σ={duration_stdev:.1f})")


@dataclass
class FetchResult:
    ms_to_first_result: int
    ms_to_last_result: int
    ms_queued: int
    num_results: int


async def fetch_one(
    session: aiohttp.ClientSession, base_url: str, *, keyword: str, delay_secs: float
) -> FetchResult:
    await asyncio.sleep(delay_secs)

    start_time_secs = time.time()
    async with session.get(
        f"{base_url}/concordance/concord?w={urllib.parse.quote(keyword)}"
    ) as response:
        assert response.status == 200, f"got HTTP error status: {response.status}"

        first_result_time_secs = None
        queued_time_secs = None
        num_results = 0
        async for line in response.content:
            msg = json.loads(line)
            assert isinstance(msg, dict)
            if "status" in msg:
                if msg["status"] == "ready":
                    queued_time_secs = time.time()
                continue

            if first_result_time_secs is None:
                first_result_time_secs = time.time()

            num_results += 1

        last_result_time_secs = time.time()
        if first_result_time_secs is None:
            first_result_time_secs = last_result_time_secs

        ms_to_first_result = int((first_result_time_secs - start_time_secs) * 1000)
        ms_to_last_result = int((last_result_time_secs - start_time_secs) * 1000)
        ms_queued = (
            int((queued_time_secs - start_time_secs) * 1000)
            if queued_time_secs is not None
            else 0
        )

        return FetchResult(
            ms_to_first_result=ms_to_first_result,
            ms_to_last_result=ms_to_last_result,
            ms_queued=ms_queued,
            num_results=num_results,
        )


def main_logs() -> None:
    rshell("journalctl -u fast-concordance")


def main_status() -> None:
    rshell("systemctl status fast-concordance")


cmd = command.Group(help="Umbrella command for fast-concordance")
cmd.add2("deploy", main_deploy, help="Deploy the server.")
cmd.add2("deploy-benchmark", main_deploy_benchmark, help="Deploy the benchmark binary.")
cmd.add2("load-test", main_load_test, help="Load-test the server.")
cmd.add2("logs", main_logs, help="Display server logs.")
cmd.add2("status", main_status, help="Display server status.")

if __name__ == "__main__":
    command.dispatch(cmd)
