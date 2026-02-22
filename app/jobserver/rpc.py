import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from lib import kgjson, oshelper
from iafisher_foundation.prelude import *

from . import server_state

# TODO(2025-11): central registry of known RPC ports
PORT = 6500


@dataclass
class ListJobsRequest(kgjson.Base):
    pass


@dataclass
class ListJobsResponse(kgjson.Base):
    jobs: List[server_state.Job]


class GenericRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        try:
            payload = json.loads(body.decode("utf8"))
            method = payload["method"]
            data = payload["data"]
        except Exception:
            LOG.error("failed to parse HTTP request as JSON", exc_info=True)
            self.send_response(400)
            self.end_headers()
            return

        handler = getattr(self, "rpc_" + method.replace(".", "__"), None)
        if handler is None:
            LOG.error("unknown RPC method: %s", method)
            self.send_response(400)
            self.end_headers()
            return

        try:
            response = handler(data)
        except Exception:
            LOG.error("RPC handler for %r raised an exception", method, exc_info=True)
            self.send_response(500)
            self.end_headers()
            return

        response_data = response.serialize().encode("utf8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(response_data)))
        self.end_headers()
        self.wfile.write(response_data)


class RequestHandler(GenericRequestHandler):
    def rpc_jobserver__list_jobs(self, _request: kgjson.Base) -> ListJobsResponse:
        # TODO: pass in state from server
        with oshelper.LockFile(server_state.state_lock_file_path(), exclusive=False):
            state = server_state.load_state_holding_lock()

        return ListJobsResponse(jobs=state.jobs)


def run_in_background_thread(port: int = PORT) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), RequestHandler)

    def main():
        server.serve_forever()

    # It's important that this is marked as a daemon thread so that it doesn't keep the whole
    # process alive if the main thread dies.
    #
    # Bug #034
    threading.Thread(target=main, name="jobserver-rpc", daemon=True).start()
    return server
