# The slim image

The upstream image is 10.6GB. `Dockerfile.slim` turns it into 1.31GB without
building anything new and without changing a line of the server's code.

## Why it is that big

One layer accounts for 6.43GB of it, the `pip install -r requirements.txt` step.
That requirements file installs `torch`, `torchaudio` and `funasr`, and pip pulls
the CUDA runtime in behind torch. Inside the image:

| | Size |
|---|---|
| `nvidia` (the CUDA runtime) | 2852 MB |
| `torch` | 1521 MB |
| `triton` | 419 MB |
| `llvmlite` and `numba` | 189 MB |
| `google` (Vertex, Cloud, generativeai) | 134 MB |
| `scipy` | 136 MB |
| `googleapiclient` | 94 MB |
| everything else in `site-packages` | about 1000 MB |
| the application itself | 28 MB |

The image ships every provider the upstream project supports, so it carries the
dependencies for local speech recognition, for a dozen model vendors, and for
four memory backends. This configuration uses one path through all of that.

## What this configuration actually needs

Speech recognition, the model and speech synthesis are all HTTP calls out of the
container, to OpenAI for the first two and to Microsoft for Edge TTS. None of
them loads a model locally. Voice activity detection does run locally, and
`core/providers/vad/silero.py` runs the `.onnx` file through `onnxruntime` on
`CPUExecutionProvider` without importing torch at all. Memory is `nomem` and
intent is `function_call`, neither of which loads anything either.

Providers are loaded by name through `importlib` in `core/utils/asr.py` and its
siblings, so the ones the config does not select are never imported. The only
thing that loads unconditionally is `plugins_func/functions/`, which
`core/connection.py` walks at import time, and those files need `bs4`,
`markitdown` and `cnlunar`. All three stay.

## How the list was decided

The list was measured rather than reasoned about. The server was started under a
wrapper that recorded `sys.modules` after a full conversation had gone through
it, including
real audio, the OpenAI transcription, the model call, Edge TTS, and an MCP tool
call. That produced 206 top level module names. Nothing on the delete list
appears in it.

The same measurement was repeated against the slim image. The two lists differ
by exactly one name, `google`, and that one was never a real import. It is a
namespace placeholder created by a `-nspkg.pth` file at interpreter startup, and
both the directory and the `.pth` files that reference it are gone.

## What was removed

89 directories in `site-packages`, 5846 MB of them, plus 80 orphaned
`.dist-info` directories. The full list is in `Dockerfile.slim`. In groups:

- The torch stack and CUDA: `nvidia`, `torch`, `torchaudio`, `torchgen`,
  `torio`, `functorch`, `triton`.
- Local speech recognition: `funasr`, `modelscope`, `sherpa_onnx`, `vosk`,
  `silero_vad` (the pip package, not the `.onnx` model, which stays in
  `models/`), `sentencepiece`, `librosa`, `soundfile`, `kaldiio` and the rest of
  the audio feature extraction chain.
- Scientific Python that only funasr and mem0 wanted: `scipy`, `sklearn`,
  `sympy`, `networkx`, `numba`, `llvmlite`, `joblib`, `umap`.
- Google client libraries: `google`, `googleapiclient`, `grpc`, `vertexai`,
  `httplib2`.
- Database drivers for the memory backends: `sqlalchemy`, `psycopg`,
  `psycopg2`, `pymysql`, `aiomysql`, `pgvector`, `qdrant_client`.
- Model vendor SDKs this server does not call: `anthropic`, `together`,
  `ollama`, `dashscope`, `cozepy`, `zai`, `mem0`, `powermem`.
- Alibaba and Baidu service clients: `aliyunsdkcore`, `oss2`, `aip`.

`numpy`, `onnxruntime`, `openai`, `edge_tts`, `opuslib_next`, `pydub`, `mcp`,
`markitdown`, `bs4`, `cnlunar`, `PIL` and everything else the running server
touches are untouched, at the exact versions upstream shipped.

## Why it is built this way

Deleting files in a new Docker layer does not make the image smaller. It writes
whiteout entries and the old layer is still there. So `Dockerfile.slim` prunes in
one stage, then copies the pruned filesystem into a `FROM scratch` stage, which
flattens everything into a single layer with no history. The metadata that
upstream set with `ENV`, `WORKDIR` and `CMD` is restated at the bottom, because
`scratch` has none of it.

The alternative was a fresh build from `python:3.10-slim` against a trimmed
requirements file. That would land in roughly the same place on size and would
change the Python build, the Debian release, the glibc version and every pinned
package that pip resolves differently on a later day. Starting from the upstream
image keeps all of that identical, and the only difference between the two images
is which directories exist.

## Rebuilding it

```bash
docker build -f Dockerfile.slim -t cat-server:slim .
```

It takes under a minute, since nothing is downloaded or compiled. If upstream
publishes a new `server_latest` and it adds a provider you want, pull the new
image and rebuild. If the delete list ever removes something a future version
needs, the failure is a `ModuleNotFoundError` at startup and the fix is to take
that name out of the list.

To go back to stock, put the upstream tag on the `image:` line in
`docker-compose.yml` and run `.\cat.ps1 restart`. Nothing else in the repo knows
about the slim image.

## What was verified

Against the slim image, on a container with the same mounts as the real one:

- Startup with no import error, and all six components initialised.
- `GET` and `POST` on `/xiaozhi/ota/` returning 200 with
  the websocket address for this machine in the body.
- `tools/fake_cat.py` holding a conversation, so the model and Edge TTS both
  ran, with opus frames coming back.
- Real audio in. A sentence was synthesised, encoded to 60ms opus frames and
  streamed the way the device streams it. The server decoded it, sent it to
  OpenAI, and the transcription came back, which is the only test that exercises
  `OpenaiASR` rather than the text shortcut `fake_cat` uses.
- Both mounted patch files loading, with `push bridge listening on 8004` in the
  log, and `/devices`, `/say` and `/face` all answering on that port.
- The `claude-code` MCP server starting inside the container and reporting
  `claude_status` and `claude_sessions`, then the model calling `claude_status`
  during a conversation.

The physical cat was not power cycled during any of this, so the only client
tested was `fake_cat.py`. It connects with the same headers and the same hello
frame the firmware sends, so there is no server side difference between them,
but that is reasoning rather than a measurement.
