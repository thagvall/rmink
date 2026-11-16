# Plugins, content packs and transports

rmink can be extended from outside in two ways:

- **A content pack** is a folder of TOML files: knowledge, symbols and workbook groups. It needs no code.
- **A plugin** is a Python package that brings one or more parts: a transport, a content pack, a file format in or out, a command, or MCP tools.

The diagram [docs/diagrams/teknik/20-plugin-och-transporter](diagrams/teknik/20-plugin-och-transporter.svg) shows the parts, where they attach and three examples.

There is a working example of every part in [`examples/rmink-plugin-exempel`](../examples/rmink-plugin-exempel). Copy it and keep what you need.

```bash
rmink plugins                 # what is installed, and whether each part loads
rmink plugins check FOLDER    # check a content pack
RMINK_NO_PLUGINS=1 rmink ...  # run without any of them
```

## Without reMarkable Cloud: transports

A transport is where rmink leaves notebooks and fetches them: a tree of folders with a `.rmdoc` per notebook. Drawings, workbooks and sheets go their rounds the same way over any of them, with the same `rmink/...` paths.

| Transport | Spec | What it is |
|---|---|---|
| reMarkable Cloud | `cloud` | The default once `rmink cloud connect` has run. Needs [rmapi](https://github.com/ddvk/rmapi). |
| The cable | `usb` | The tablet's USB web interface at 10.11.99.1. No subscription. It cannot make or move folders; see below. |
| A folder | `folder:PATH` | `/rmink/Bygg/Altan/Altan r02` is `PATH/rmink/Bygg/Altan/Altan r02.rmdoc`. |
| From a plugin | `NAME:ARG` | Whatever the plugin brings. |

Choose one for good, or for one command:

```bash
rmink transport use folder:~/Documents/rmink    # saved in ~/.config/rmink/config.toml
rmink --via folder:~/Documents/rmink sheet send ritning.pdf --send
RMINK_TRANSPORT=folder:~/Documents/rmink rmink mcp
rmink transport list                            # the transports there are, and the one in use
rmink transport ls /rmink
```

`--via` goes before the command. The order is `--via` or `$RMINK_TRANSPORT`, then the saved choice, then the cloud when connected.

**The folder is a handover point, not a connection to the tablet.** rmink puts `Altan r02.rmdoc` in the folder and expects to find the notebook you wrote on there again under the same name. What carries files between the folder and the tablet is up to you: a sync tool, a server of your own, or dragging them into the USB web interface. To have rmink talk to the tablet itself without the cloud, use `usb`.

### Over the cable: `usb`

Plug the tablet in, wake it, and turn on *Settings → Storage → USB web interface* (called *USB connection* on newer system software). Then:

```bash
rmink --via usb transport check     # does it answer, and can it hand out notebooks?
rmink transport use usb             # use it for everything; usb:HOST for another address
```

The interface lists folders, hands out a notebook as `.rmdoc` (system software 3.9 and later) and takes an upload into a folder. It has no way to make, move, rename or remove anything, so:

- **Make the folders on the tablet yourself.** When one is missing, rmink stops and names it (`Make the folder "/rmink/Ark" on the tablet`). A drawing needs `rmink/Bygg/<name>`, a sheet `rmink/Ark`.
- **Nothing moves to `Tidigare`.** After a round the notebook that was read stays beside the new revision, and rmink logs that it could not move it.
- **Two notebooks can have one name** on the tablet; rmink reads the one changed last.
- Files over 100 MB are refused, as the interface does.

Measured on an rm2: an upload lands in the folder listed last, and the tablet names it after the name inside the archive, which rmink sets. The interface is documented by its users, not by reMarkable, and may change with the tablet's software.

The hosted web app only sends through the cloud. Transports are for the CLI and the MCP server, which run on your own computer.

### Writing a transport

A transport is an object with six methods. Paths are absolute, with `/` between folders, and a notebook's path has no file extension.

```python
from pathlib import Path
from rmink.transport import Entry, ExistsError, NotFoundError, TransportError

class MyTransport:
    name = "mine"

    def ls(self, path: str = "/") -> list[Entry]: ...   # Entry(name, folder); NotFoundError without the path
    def get(self, path: str) -> bytes: ...              # the notebook as .rmdoc bytes
    def put(self, file: Path, folder: str = "/", name: str | None = None) -> str: ...
    def mkdir(self, path: str) -> None: ...             # the parent must exist; already there is fine
    def mv(self, src: str, dst: str) -> None: ...       # ExistsError when dst is taken
    def rmdir(self, path: str) -> None: ...             # empty folders only

def open(arg: str) -> MyTransport:                      # what follows "mine:"
    return MyTransport(arg)
```

```toml
[project.entry-points."rmink.transports"]
mine = "rmink_mine:open"
```

What rmink relies on:

- `put` returns the name it used. When the name is taken it uses `name_2`, `name_3` and so on, never overwrites.
- `ls` of a folder that is not there raises `NotFoundError`; rmink then makes the folders one by one with `mkdir`.
- `mv` moves a notebook or a whole folder and raises `ExistsError` when the target name is taken; rmink then tries the next name.
- Errors are `TransportError` or a subclass, with a message that can be shown to the user. Anything else is a bug in the transport.
- A transport gets the files, never the user's reMarkable token.

`rmink.transport.FolderTransport` does all of this for a directory. A transport that can mount or unpack its tree somewhere can hand the work to it, as the example's `zip:` transport does in thirty lines.

## Content packs

```
my-pack/
  pack.toml            name, version, description, api = 1
  knowledge/*.toml     the file names and tables of src/rmink/knowledge/data
  workbook/*.toml      [[group]] tables as in src/rmink/workbook/data/skola.toml
```

Packs are read on top of what rmink ships, later ones over earlier:

1. packages with an `rmink.packs` entry point,
2. the folders in `~/.config/rmink/packs/`,
3. your own loose files in `~/.config/rmink/knowledge/` and `~/.config/rmink/workbook/` (no `pack.toml` needed).

An entry with the `id` of one that is already there replaces it; any other is added. Each entry from a pack carries a `pack` field with the pack's name, which `lookup_knowledge` shows, so it is clear where a fact came from.

**Knowledge.** The files are `terms`, `drawing_standard`, `symbols`, `materials`, `assemblies`, `rules`, `markup`, `hatches` and `process`. An entry needs every field that all of rmink's own entries in that table have, and what it refers to (a material's hatch, an assembly's materials, a symbol's rules) must exist. `rmink plugins check` reports what is missing. At run time an entry with a fault is left out with a warning, so a broken pack never stops a round.

**Symbols.** A `[[symbol]]` in `knowledge/symbols.toml` with `paths` is drawn like a built-in one: on the page, in the legend, and as SVG for Open PDF Studio's library. `paths` is a list of polylines in the unit box, x and y from -0.5 to 0.5 with y down:

```toml
[[symbol]]
id = "sauna_heater"
name = "Bastuaggregat"
# ... the other fields of symbols.toml ...
paths = [
    [[-0.4, 0.0], [0.4, 0.0], [0.4, 0.5], [-0.4, 0.5], [-0.4, 0.0]],
    [[0.0, -0.1], [0.1, -0.25], [0.0, -0.4], [0.1, -0.5]],
]
```

**Workbook groups.** A `[[group]]` with its `[[group.topic]]` tables becomes a group in rmink skola: a folder under `rmink/Skola/` and topics with briefs for Claude.

To ship a pack as a package, point the entry point at the package that holds `pack.toml`:

```toml
[project.entry-points."rmink.packs"]
exempel = "rmink_exempel"
```

## File formats

**In.** An importer reads a file type rmink does not know and returns pages. It is named after the suffix.

```python
from rmink.ingest import RasterSource, VectorShape, VectorSource

def load(path, mode, pages=None) -> list[VectorSource | RasterSource]: ...
```

```toml
[project.entry-points."rmink.importers"]
geojson = "rmink_exempel:load_geojson"
```

A `VectorSource` has a width and height and shapes with y down; `px_per_unit_at_dpi` says how large a unit is (the default is points, 1/72 inch). After that `rmink convert file.geojson`, the web UI and the MCP tools take the new type. Raise `ValueError` with a message for the user when the file cannot be read.

**Out.** An exporter turns a clean drawing (`rmink.drawing.model.Drawing`) into another program's format. It is named after the format and returns `bytes` or `str`.

```toml
[project.entry-points."rmink.exporters"]
geojson = "rmink_exempel:export_geojson"
```

```bash
rmink export Altan --format geojson -o altan.geojson
```

`pdf` and `svg` are built in. The MCP tool is `export_drawing`.

## Commands and MCP tools

```toml
[project.entry-points."rmink.commands"]
exempel = "rmink_exempel:app"          # a typer.Typer, or a plain function: `rmink exempel`

[project.entry-points."rmink.mcp_tools"]
exempel = "rmink_exempel:register"     # register(server) adds tools with @server.tool()
```

## Rules for all plugins

- **Built-in names stay.** A plugin cannot replace `cloud`, `folder` or `usb`, `.pdf`, the `pdf` export or `rmink convert`. Pack data is the exception: the same `id` replaces on purpose.
- **Nothing is imported until it is used.** `rmink convert` does not import your transport. Keep imports of heavy libraries inside the functions that need them.
- **A plugin that fails is skipped** with a warning; `rmink plugins` says why.
- **`rmink.plugins.API_VERSION` is 1.** The entry point groups, the `Transport` methods, the pack layout and the importer and exporter signatures above are what it covers. They will not change without the number changing; a pack says which it was written for with `api = 1`. Everything else in `rmink.*` is internal and may change between releases.
- **Name packages `rmink-<name>`** on PyPI so they can be found.
- **A plugin is code that runs as you.** Install only what you trust, as with any Python package. A content pack in `~/.config/rmink/packs/` is data and runs nothing.
