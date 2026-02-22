import shlex

from app.iafisher.common import CODE_PATH
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from iafisher_foundation.scripting import sh0
from lib import githelper, kgenv


USER = "iafisher"
SSH_KEY = pathlib.Path.home() / ".ssh" / "digital-ocean"


def remote_script(
    ip_addr: str,
    user: str,
    script_name: str,
    *args: str,
    log_to: Optional[PathLike] = None,
) -> None:
    local_path = pathlib.Path(__file__).absolute().parent / "scripts" / script_name
    remote_path = f"/tmp/{local_path.name}"
    scp(local_path.as_posix(), remote_path, user=user, hostname=ip_addr)

    ssh_cmd = (
        f"ssh -i {SSH_KEY} {user}@{ip_addr} bash -e {remote_path} {shlex.join(args)}"
    )
    if log_to is not None:
        os.makedirs(os.path.dirname(log_to), exist_ok=True)
        ssh_cmd = f"{ssh_cmd} 2>&1 | tee -a {log_to}"

    local(ssh_cmd)
    local(f"ssh -i {SSH_KEY} {user}@{ip_addr} rm -f {remote_path}")


def scp(local_path: str, remote_path: str, *, user: str, hostname: str) -> None:
    local(f"scp -i {SSH_KEY} {local_path} {user}@{hostname}:{remote_path}")


def local(cmd: str) -> None:
    sh0(cmd)


def main_provision(ip_addr: str) -> None:
    scp(f"{SSH_KEY}.pub", "/root/authorized_keys", user="root", hostname=ip_addr)
    log_to = get_logs_path("provision")
    remote_script(ip_addr, "root", "provision_001_root_create_user.bash", log_to=log_to)
    remote_script(ip_addr, USER, "provision_002_iafisher_provision.bash", log_to=log_to)


def main_deploy() -> None:
    os.chdir(CODE_PATH)

    if githelper.current_branch() != "master":
        confirm_or_bail("Deploy from non-master branch? ")

    if githelper.are_there_uncommitted_changes():
        confirm_or_bail(
            "The Git repo has uncommitted changes. Continue and deploy these changes? "
        )

    print("==> building frontend code")
    sh0("npm run build-prod")

    print("==> bundling up server code")
    last_commit_hash = githelper.last_commit_hash()
    archive_filename = f"iafisher-code-{last_commit_hash}.tar.gz"
    archive_local_filepath = f"/tmp/{archive_filename}"
    git_exclude_cmd = "git ls-files --exclude-standard -oi --directory | grep -v backend/sitemod/static/bundles/"
    sh0(
        f"tar --no-xattrs -czf {archive_local_filepath} --exclude-from=<({git_exclude_cmd}) --exclude-vcs ."
    )

    try:
        hostname = "iafisher.com"
        archive_remote_filepath = f"/var/iafisher/deployments/{archive_filename}"
        scp(
            archive_local_filepath,
            archive_remote_filepath,
            user=USER,
            hostname=hostname,
        )
        remote_script(
            hostname,
            USER,
            "deploy.bash",
            archive_remote_filepath,
            log_to=get_logs_path("deploy"),
        )
    finally:
        sh0(f"rm -f {archive_local_filepath}")


def main_list_deploys() -> None:
    sh0(f"ssh -i {SSH_KEY} iafisher.com 'cd /var/iafisher/deployments && ls -ltd *'")


def main_rollback(old_deploy: str) -> None:
    remote_script(
        "iafisher.com",
        USER,
        "rollback.bash",
        f"/var/iafisher/deployments/{old_deploy}",
        log_to=get_logs_path("rollback"),
    )


def get_logs_path(job_name: str) -> pathlib.Path:
    now = timehelper.now()
    return (
        kgenv.get_ian_dir()
        / "logs"
        / f"iafisher::{job_name}"
        / (now.isoformat() + ".log")
    )
