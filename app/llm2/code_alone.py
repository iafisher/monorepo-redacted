import html
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Annotated

from app.llm2 import common
from app.llm2.code import Hooks as VerboseHooks
from iafisher_foundation.prelude import *
from iafisher_foundation.scripting import q, sh0
from lib import command, kgjson, githelper, kgenv, llm, pdb, simplemail


@dataclass
class Request(kgjson.Base):
    request_id: str
    llm_conversation_id: int
    prompt: str


REQUEST_DIR = kgenv.get_ian_dir() / "apps" / "llm2" / "code-alone" / "requests"


SYSTEM_PROMPT = """\
You are a senior software engineer LLM working on a code repository.

You are given tools that allow you to explore and manipulate the repository.

For tasks that require multiple steps, write out a plan using the scratchpad tool first.
At the end, check the scratchpad to make sure you've done everything you planned to.
You don't need to use the scratchpad for small tasks.

You are typically invoked non-interactively, in a sandboxed environment (e.g., a Docker
container) without network access. There may be previous messages in the chat history
from a different interface, for context. You should complete the task as best as you can.
Do not stop to ask a question, because the user is not there to answer it.

You can run project tests with `./do test <module>`. For example, to run the tests in
`lib/kghttp`, run `./do test kghttp`. Some tests might not pass because the sandbox does
not have access to the outside Internet.

You should NOT use the `git` binary to make any changes.
"""


def main_accept(
    request_id: str,
    *,
    code_dir: Annotated[
        Optional[pathlib.Path], command.Extra(help="defaults to $KG_CODE_DIR")
    ] = None,
    even_if_unclean: Annotated[
        bool, command.Extra(help="apply the patch even if `git status` is unclean")
    ],
) -> None:
    machine = kgenv.get_machine()
    if machine != kgenv.MACHINE_LAPTOP:
        raise KgError("This command can only be run from my laptop.", machine=machine)

    if code_dir is None:
        code_dir = kgenv.get_code_dir()

    os.chdir(code_dir)
    if not even_if_unclean and githelper.are_there_uncommitted_changes():
        raise KgError(
            "The repository has uncommitted changes."
            " Commit them, stash them, or re-run with -even-if-unclean to apply the patch anyway.",
            directory=code_dir,
        )

    patch_file_path = _get_patch_file_path(request_id, ian_dir=kgenv.get_ian_dir())
    if patch_file_path.exists():
        _accept_local_patch_file(patch_file_path)
    else:
        _accept_remote_patch_file(request_id)


def _accept_local_patch_file(patch_file_path: pathlib.Path) -> None:
    sh0(f"git apply {q(patch_file_path.as_posix())}")


def _accept_remote_patch_file(request_id: str) -> None:
    remote_path = _get_patch_file_path(
        request_id, ian_dir=pathlib.Path("/home/iafisher/.ian")
    )
    sh0(
        f"ssh homeserver cat {q(remote_path.as_posix())}" " | git apply -",
    )
    sh0(f"ssh homeserver rm {q(remote_path.as_posix())}")


def main_check_for_requests(
    *,
    verbose: bool = False,
    preserve_temp_dir: bool = False,
    code_dir: Annotated[
        Optional[pathlib.Path], command.Extra(help="defaults to $KG_CODE_DIR")
    ] = None,
) -> None:
    if not REQUEST_DIR.exists():
        LOG.warning("request directory does not exist, doing nothing: %s", REQUEST_DIR)
        return

    try:
        request_file = next(REQUEST_DIR.iterdir())
    except StopIteration:
        LOG.info("request directory empty, doing nothing: %s", REQUEST_DIR)
    else:
        LOG.info("found request file: %s", request_file)
        request = Request.load(request_file)
        LOG.info("got request: %r", request)
        # Delete the request file at the beginning. This ensures that if there is a bug, we don't
        # loop endlessly on the same request and burn tokens. We logged the full request above to
        # allow us to recover manually from errors.
        request_file.unlink()
        LOG.info("deleted request file: %s", request_file)

        with pdb.connect() as db:
            conversation = llm.Conversation.fork(db, request.llm_conversation_id)
            _code_alone(
                db,
                conversation,
                request_id=request.request_id,
                prompt=request.prompt,
                verbose=verbose,
                preserve_temp_dir=preserve_temp_dir,
                code_dir=code_dir,
            )


def main_prompt(
    *,
    prompt: str,
    model: str = llm.CLAUDE_SONNET_4_6,
    verbose: bool = False,
    preserve_temp_dir: bool = False,
) -> None:
    with pdb.connect() as db:
        conversation = llm.Conversation.start(
            db,
            model=model,
            app_name="llm2::code-alone",
            # this is set in `_code_alone`
            system_prompt="",
        )
        request_id = str(uuid.uuid4())
        LOG.info("request ID: %s", request_id)
        _code_alone(
            db,
            conversation,
            request_id=request_id,
            prompt=prompt,
            verbose=verbose,
            preserve_temp_dir=preserve_temp_dir,
            code_dir=None,
        )


def _code_alone(
    db: pdb.Connection,
    conversation: llm.Conversation,
    *,
    request_id: str,
    prompt: str,
    verbose: bool,
    preserve_temp_dir: bool,
    code_dir: Optional[pathlib.Path],
) -> None:
    if code_dir is None:
        code_dir = kgenv.get_code_dir()

    docker_details = set_up_docker(code_dir)
    container_id = docker_details.container_id
    temp_dir = docker_details.temp_dir

    try:
        scratchpad = llm.tools.Scratchpad()
        tools: List[llm.BaseTool] = [
            # file retrieval tools
            llm.tools.FindFileTool(temp_dir),
            llm.tools.ListFilesTool(temp_dir),
            llm.tools.ReadFileTool(temp_dir),
            llm.tools.SearchFileContentsTool(temp_dir),
            # file manipulation tools
            llm.tools.CreateEmptyDirectory(temp_dir, auto_approve=True),
            llm.tools.CreateFileTool(temp_dir, auto_approve=True),
            llm.tools.ReplaceInFileTool(temp_dir, auto_approve=True),
            llm.tools.DockerBashCommandTool(
                container_id, docker_details.container_workdir
            ),
            # scratchpad tools
            llm.tools.GetScratchpadTool(scratchpad),
            llm.tools.SetScratchpadTool(scratchpad),
        ]
        system_prompt = SYSTEM_PROMPT + common.get_agents_file(code_dir)
        model_response = conversation.prompt(
            db,
            prompt,
            options=llm.InferenceOptions.slow(),
            tools=tools,
            hooks=VerboseHooks() if verbose else llm.BaseHooks(),
            override_system_prompt=system_prompt,
        )

        githelper.add_all(repo=temp_dir)
        patch = githelper.diff(repo=temp_dir)
        patch_file_path = _get_patch_file_path(request_id, ian_dir=kgenv.get_ian_dir())
        patch_file_path.parent.mkdir(parents=True, exist_ok=True)
        patch_file_path.write_text(patch)
        LOG.info("wrote to %s", patch_file_path)

        diff_as_html = githelper.diff_to_html(patch)
        send_email(
            prompt,
            model_response.output_text,
            diff_as_html,
            conversation_id=conversation.conversation_id,
            request_id=request_id,
        )
    finally:
        LOG.info("stopping docker container %s", container_id)
        clean_up_docker(container_id)

        if not preserve_temp_dir:
            LOG.info("removing temporary directory: %s", temp_dir)
            shutil.rmtree(temp_dir)


def send_email(
    prompt: str,
    model_output: str,
    diff_as_html: str,
    *,
    conversation_id: int,
    request_id: str,
) -> None:
    body = EMAIL_TEMPLATE % dict(
        prompt=html.escape(prompt),
        model_output=html.escape(model_output),
        diff_as_html=diff_as_html,
        conversation_id=conversation_id,
        request_id=request_id,
    )
    simplemail.send_email(
        subject="LLM code-alone task completed",
        body=body,
        recipients=[simplemail.LOW_PRIORITY_RECIPIENT],
        html=True,
    )


EMAIL_TEMPLATE = """\
<p>
  An LLM finished its code-alone task (conversation ID: %(conversation_id)s).
  If you are satisfied with the diff, run (on the laptop):
</p>

<pre><code>llm2 code-alone accept %(request_id)s</code></pre>

<h2>Prompt</h2>
<pre><code>%(prompt)s</code></pre>

<h2>Model message</h2>
<pre><code>%(model_output)s</code></pre>

<h2>Diff</h2>
%(diff_as_html)s
"""


def main_test_email() -> None:
    # a random commit from the monorepo
    test_commit = "08bb7d5b89e1e0eec4d963262851b1c5c8d535a9"
    diff_as_html = githelper.diff_to_html(
        githelper.diff([f"{test_commit}~1", test_commit], repo=kgenv.get_code_dir())
    )
    send_email(
        "This is a test prompt.",
        "This is test model output.",
        diff_as_html,
        conversation_id=-1,
        request_id="test-request-id",
    )


def main_test_docker(
    *,
    pause: Annotated[
        bool, command.Extra(help="pause before cleaning up the container")
    ],
) -> None:
    details = set_up_docker(kgenv.get_code_dir())

    print()
    print()
    print(f"Container ID:        {details.container_id}")
    print(f"Temporary directory: {details.temp_dir}")

    print()
    print("Running test...")
    subprocess.run(
        [
            "docker",
            "exec",
            "-w",
            details.container_workdir,
            details.container_id,
            "bash",
            "-c",
            "./do test humanunits",
        ],
        check=True,
    )

    if pause:
        print()
        print("Press <Enter> to kill container and clean up.")
        input()

    print("Cleaning up...")
    clean_up_docker(details.container_id)
    shutil.rmtree(details.temp_dir)


@dataclass
class DockerDetails:
    container_id: str
    image_tag: str
    temp_dir: pathlib.Path
    container_workdir: str


DOCKER_IMAGE_TAG = "llm2-code-alone"
DOCKERFILE_PATH = pathlib.Path(__file__).parent / "docker" / "Dockerfile"
DOCKER_CONTEXT_DIR = DOCKERFILE_PATH.parent
READY_FILE_NAME = ".llm2_docker_ready"


def set_up_docker(code_dir: pathlib.Path) -> DockerDetails:
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="llm-workspace-"))
    LOG.info("cloning git repository to %s", temp_dir)
    githelper.clone(code_dir, to_=temp_dir)

    container_workdir = "/workspace"
    uid = os.getuid()
    gid = os.getgid()

    if not DOCKERFILE_PATH.exists():
        raise KgError("Dockerfile missing.", dockerfile=DOCKERFILE_PATH)

    LOG.info("building docker image %s", DOCKER_IMAGE_TAG)
    subprocess.run(
        [
            "docker",
            "build",
            "-t",
            DOCKER_IMAGE_TAG,
            "-f",
            DOCKERFILE_PATH.as_posix(),
            "--build-arg",
            f"USER_ID={uid}",
            "--build-arg",
            f"GROUP_ID={gid}",
            DOCKER_CONTEXT_DIR.as_posix(),
        ],
        check=True,
    )

    container_id = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-v",
            f"{temp_dir}:{container_workdir}",
            "-e",
            f"KG_CODE_DIR={container_workdir}",
            DOCKER_IMAGE_TAG,
        ],
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    ).stdout.strip()
    LOG.info("started docker container %s", container_id)

    _wait_for_docker_ready(container_id, temp_dir)

    LOG.info("disconnecting docker container from network")
    subprocess.run(
        ["docker", "network", "disconnect", "bridge", container_id], check=True
    )

    return DockerDetails(
        container_id=container_id,
        image_tag=DOCKER_IMAGE_TAG,
        temp_dir=temp_dir,
        container_workdir=container_workdir,
    )


def _wait_for_docker_ready(
    container_id: str, temp_dir: pathlib.Path, timeout_seconds: float = 600.0
) -> None:
    ready_file = temp_dir / READY_FILE_NAME
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if ready_file.exists():
            LOG.info("docker container ready: %s", ready_file)
            return

        running = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        if running != "true":
            raise KgError(
                "Docker container exited during setup.", container_id=container_id
            )

        time.sleep(1.0)

    raise KgError(
        "timed out waiting for Docker container to finish setup",
        container_id=container_id,
        timeout_seconds=timeout_seconds,
    )


def clean_up_docker(container_id: str) -> None:
    subprocess.run(["docker", "stop", container_id])
    subprocess.run(["docker", "rm", container_id])


def _get_patch_file_path(request_id: str, *, ian_dir: pathlib.Path) -> pathlib.Path:
    return (
        ian_dir
        / "apps"
        / "llm2"
        / "code-alone"
        / "patches"
        / f"request-{request_id}.patch"
    )


cmd = command.Group(help="An unsupervised, sandboxed coding agent for the monorepo.")
cmd.add2("accept", main_accept, help="Accept a diff generated by an agent.")
cmd.add2(
    "check-for-requests",
    main_check_for_requests,
    less_logging=False,
    help="Check for enqueued requests and execute the first one.",
)
cmd.add2("prompt", main_prompt, less_logging=False, help="Prompt the agent.")
test_cmd = command.Group(help="Subcommands for testing.")
test_cmd.add2("email", main_test_email, help="Send a test email.")
test_cmd.add2("docker", main_test_docker, help="Test the Docker container.")
cmd.add("test", test_cmd)
