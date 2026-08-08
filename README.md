# FrameXML Intrinsic Parser

### `main.py`

`main.py` runs the show - using the modules from `scraper/` it scrapes information from [FrameXML](https://warcraft.wiki.gg/wiki/FrameXML), finds all the [intrinsic frame](https://warcraft.wiki.gg/wiki/Intrinsic_frame) definitions, their [mixins](https://warcraft.wiki.gg/wiki/API_Mixin) and the mixins' methods, as well as any related [virtual templates](https://warcraft.wiki.gg/wiki/Virtual_XML_template), finally writing wiki pages to `pages/`.

Any structures used as types in the method pages that exist in the scraped files will also be templated into pages.

This runs on an interval through GitHub workflows once a week (the day after PTR builds typically release), and creates pull requests for any new or modified pages.

## Runtime dependencies

- [Python](https://www.python.org) 3.12 or newer
- `requirements.txt`
