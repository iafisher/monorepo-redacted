A Chrome extension to copy-edit Wikipedia pages with an LLM.

It's more complex than you would expect because Wikipedia's editor uses CodeMirror, which means
that replacing the editor's text is not as simple as `textarea.value = "..."` – we have to use
CodeMirror APIs.

The browser extension runs in a different JavaScript domain than CodeMirror, though, so we
inject a content script into the page (`codemirror.ts` is the script; `bridge.ts` does the
injecting) and use `window.postMessage` to communicate with it.

Otherwise this is a thin extension which just makes an HTTP request to the backend server (see
`app/wikipedia`) and shows some UI elements.

To deploy:

- Run `npm run build`
- Go to chrome://extensions and reload.
