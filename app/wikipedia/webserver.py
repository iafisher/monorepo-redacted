import urllib.parse

import flask

from app.wikipedia import rpc, tidy
from iafisher_foundation.prelude import *
from lib import llm, webserver


app = webserver.make_app("wikipedia", file=__file__)


def _normalize_cors_origin(origin: Optional[str]) -> Optional[str]:
    if not origin:
        return None

    parsed = urllib.parse.urlparse(origin)
    if parsed.scheme != "https" or not parsed.hostname:
        return None

    if parsed.hostname == "wikipedia.org" or parsed.hostname.endswith(".wikipedia.org"):
        return origin

    return None


def _apply_cors(response: flask.Response) -> flask.Response:
    origin = _normalize_cors_origin(flask.request.headers.get("Origin"))
    if not origin:
        return response

    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Max-Age"] = "600"
    response.headers["Vary"] = "Origin"
    return response


@app.after_request
def add_cors_headers(response: flask.Response) -> flask.Response:
    return _apply_cors(response)


@app.route("/tidy/llm", methods=["POST", "OPTIONS"])
def api_tidy_llm():
    if flask.request.method == "OPTIONS":
        return _apply_cors(flask.Response(status=204))

    request = webserver.request(rpc.CopyEditLLMRequest)
    if request.text.strip() == "":
        return webserver.json_response_error("text was blank")

    model_name = request.model or llm.CLAUDE_SONNET_4_6
    try:
        LOG.info("LLM call started")
        edited_text, response = tidy.tidy(request.text, model=model_name)
        LOG.info("LLM call finished")
    except Exception as e:
        LOG.exception("copyedit failed")
        return webserver.json_response_error(f"LLM call failed: {e}")

    return webserver.json_response2(
        rpc.CopyEditLLMResponse(
            edited_text=edited_text,
            model=response.model,
            conversation_id=response.conversation_id,
        )
    )


@app.route("/tidy/regex", methods=["POST", "OPTIONS"])
def api_tidy_regex():
    if flask.request.method == "OPTIONS":
        return _apply_cors(flask.Response(status=204))

    request = webserver.request(rpc.CopyEditRegexRequest)
    if request.text.strip() == "":
        return webserver.json_response_error("text was blank")

    edited_text = tidy.tidy_regex(request.text)
    return webserver.json_response2(rpc.CopyEditRegexResponse(edited_text=edited_text))


cmd = webserver.make_command(app, default_port=7800)
