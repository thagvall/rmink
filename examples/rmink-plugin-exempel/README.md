# rmink-exempel

An example plugin for [rmink](https://github.com/thagvall/rmink): one small part of
each kind a package can bring. Copy it, rename it `rmink-<yours>`, keep what you need.

```
pip install -e examples/rmink-plugin-exempel
rmink plugins
```

| Part | What it does | Try it |
|---|---|---|
| Transport `zip:` | The whole notebook tree in one zip file, easy to mail or carry | `rmink --via zip:~/rmink.zip transport ls` |
| Content pack | A sauna heater symbol, a term and a workbook group, as TOML | `rmink plugins check examples/rmink-plugin-exempel/src/rmink_exempel` |
| Importer `.geojson` | Lines and polygons from a GIS file become ink | `rmink convert tomt.geojson` |
| Exporter `geojson` | A clean drawing's elements as GeoJSON | `rmink export Altan --format geojson` |
| Command | `rmink exempel` | `rmink exempel` |
| MCP tool | `exempel_info` in `rmink mcp` | |

Everything is in `src/rmink_exempel/__init__.py` and the TOML files beside it. The
interfaces are described in rmink's `docs/plugins.md`.
