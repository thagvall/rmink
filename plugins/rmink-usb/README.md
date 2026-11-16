# rmink-usb

A transport for [rmink](https://github.com/thagvall/rmink) over the reMarkable USB web
interface, for rounds without a reMarkable Cloud subscription.

```bash
pip install -e plugins/rmink-usb     # from a checkout of rmink
rmink usb                            # does the tablet answer, and what can it do?
rmink --via usb sheet send ritning.pdf --send
rmink transport use usb              # use it for everything
```

Plug the tablet in with the cable, wake it, and turn on *Settings → Storage → USB web
interface* (called *USB connection* on newer system software). The address is
`10.11.99.1`; `usb:HOST` uses another.

## What it can and cannot do

The interface lists folders, hands out a notebook as `.rmdoc` (system software 3.9 and
later) and takes an upload into a folder. It has no way to make, move, rename or remove
anything. So:

- **Make the folders on the tablet yourself.** When a folder is missing, rmink stops and
  names it (`Make the folder "/rmink/Ark" on the tablet`). A drawing needs
  `rmink/Bygg/<name>`, a sheet `rmink/Ark`.
- **Nothing moves to `Tidigare`.** After a round the notebook that was read stays beside
  the new revision. rmink logs that it could not move it; move it on the tablet if you
  want the folder tidy.
- **Two notebooks can have one name** on the tablet; rmink reads the one changed last.
- Files over 100 MB are refused, as the interface does.

## Status

Tried on a reMarkable 2 on 2026-11-16:

- Listing works, and folders are found by name down to `rmink/Ark`.
- A notebook comes back as `.rmdoc` with its pages and ink (a 14-page sheet in under a second).
- An upload lands in the folder that was listed last, not in the root.
- The tablet names an uploaded notebook after the `visibleName` inside the archive, not
  after the file name. The plugin therefore writes the name into the archive, which is
  also what makes `name_2` work when a name is taken.

Not tried: a full drawing or workbook round over USB, the Paper Pro and Move, and system
software before 3.9. The interface is documented by the community
([remarkable.guide](https://remarkable.guide/tech/usb-web-interface.html)), not by reMarkable,
and can change with a software update. `tests/test_usb_plugin.py` in rmink runs the
plugin against a stand-in server that behaves as measured.
