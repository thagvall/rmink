# Diagram över rmink

- **[Verksamhet](verksamhet/README.md):** processkartan och kedjediagram med roller och system. Diagrammen visar vem som gör vad längs varje process: från skiss till ritning, revisionsvarv, val mellan alternativ, bygglov och byggprocess samt bild eller PDF till reMarkable.
- **[Teknik](teknik/README.md):** 19 diagram över hur appen och kunskapsbasen är byggda. De visar arkitektur, flöden, moln och cache, ritningsmodellen, lagar och regler, ritstandard, material, konstruktioner, produktalternativ, symboler, skrafferingar och begrepp.

Alla diagram byggs ur koden och datan, och du bygger om dem med:

```
python docs/diagrams/build.py --export
```

Varje diagram finns som `.drawio`, som går att redigera i draw.io, och som `.svg`, som visas med ljus bakgrund.
