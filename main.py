import os
import sys
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from scraper import get_xml_templates, get_xml_intrinsics, get_lua_tables, Table

SOURCE_DIR = Path("wow-ui-source/Interface/AddOns")
PAGES_DIR = Path("pages")

# there are a _lot_ of templates based on intrinsics, and most of them have little value
TEMPLATES_TO_KEEP = [
  "CustomAuraButtonTemplate",
  "CustomAuraContainerTemplate",
]

jinja = Environment(
  loader=FileSystemLoader("templates"),
  extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"],
  keep_trailing_newline=True, # just good hygiene
  # wiki pages use { and } extensively, so we'll use something else for jinja
  block_start_string="[%",
  block_end_string="%]",
  variable_start_string="[[",
  variable_end_string="]]",
  comment_start_string="[#",
  comment_end_string="#]",
)

def get_inherited_mixins(tables: dict[str, Table], origins: list[str]) -> list[str]:
  mixins = []
  stack = origins.copy()

  while stack:
    mixin = stack.pop()
    if mixin not in mixins:
      mixins.append(mixin)

      for inherit in tables[mixin].inherits:
        if inherit not in mixins:
          stack.append(inherit)

  return mixins

def main() -> None:
  if not SOURCE_DIR.exists() or not SOURCE_DIR.is_dir():
    print(f"Error: directory not found: {SOURCE_DIR}", file=sys.stderr)
    sys.exit(1)

  # scrape XML intrinsics, and get a list of files they were found in
  intrinsics, intrinsic_files = get_xml_intrinsics(SOURCE_DIR)
  intrinsics_dict = {
    intrinsic["name"]: {k: v for k, v in intrinsic.items() if k != "name"}
    for intrinsic in [dict(intrinsic) for intrinsic in intrinsics]
  }

  # use the list of intrinsics files to get their upper directories,
  # stripping the base prefix for easier manipulation and appending
  intrinsic_paths = [Path(*Path(*path.parts[path.parts.index("wow-ui-source"):]).parts[3:4]) for path in intrinsic_files]

  # add extra paths we'll need for building inheritance
  intrinsic_paths.append(Path('Blizzard_SharedXMLBase'))
  intrinsic_paths.append(Path('Blizzard_Narration'))
  intrinsic_paths.append(Path('Blizzard_Menu'))

  # add prefix the prefix back to all the paths
  for index, path in enumerate(intrinsic_paths):
    intrinsic_paths[index] = SOURCE_DIR / path

  # ensure we have unique paths
  intrinsic_paths = set(intrinsic_paths)

  # scrape XML templates in the defined paths
  templates = get_xml_templates(intrinsic_paths)
  templates_dict = {
    template["name"]: {k: v for k, v in template.items() if k != "name"}
    for template in [dict(template) for template in templates]
    if template["name"] in TEMPLATES_TO_KEEP
  }

  # scrape Lua tables in the defined paths
  tables = get_lua_tables(intrinsic_paths)
  tables_dict = {
    table["name"]: {k: v for k, v in table.items() if k != "name"}
    for table in [dict(table) for _, table in tables.items()]
  }

  # manipulate the dicts
  for template in templates_dict:
    template_type = templates_dict[template]["type"]

    # inject the templates using intrinsic types into the intrinsic
    if template_type in intrinsics_dict:
      if not "templates" in intrinsics_dict[template_type]:
        intrinsics_dict[template_type]["templates"] = []
      intrinsics_dict[template_type]["templates"].append(template)

    # merge the inherited mixins into the mixins list
    mixins = get_inherited_mixins(tables, templates_dict[template]["mixins"])
    templates_dict[template]["mixins"] = mixins

  # store pages and references
  pages = {}
  referenced_mixins = {}
  referenced_types = set()

  for intrinsic in intrinsics_dict:
    # merge the inherited mixins into the mixins list
    mixins = get_inherited_mixins(tables, intrinsics_dict[intrinsic]["mixins"])
    intrinsics_dict[intrinsic]["mixins"] = mixins

    # build the intrinsic page
    print(f"Templating page INTRINSIC_{intrinsic}...", file=sys.stderr)
    template = jinja.get_template("intrinsic.j2")
    pages[f"INTRINSIC_{intrinsic}"] = template.render(
      name=intrinsic,
      data=intrinsics_dict[intrinsic],
      tables=tables,
      templates=templates_dict,
    )

    # track which mixins this intrinsic and its templates use, so we can build
    # pages for their methods
    referenced_mixins[intrinsic] = mixins
    if "templates" in intrinsics_dict[intrinsic]:
      for template in intrinsics_dict[intrinsic]["templates"]:
        referenced_mixins[intrinsic].extend(templates_dict[template]["mixins"])

  # build unique pages for the mixins' methods
  api_pages = {}
  for intrinsic, mixins in referenced_mixins.items():
    api_pages[intrinsic] = []
    for mixin in mixins:
      for method in tables_dict[mixin]["methods"]:
        if method not in api_pages[intrinsic]:
          api_pages[intrinsic].append(method)

        print(f"Templating page API/{intrinsic}_{method}...", file=sys.stderr)
        template = jinja.get_template("method.j2")
        pages[Path("API") / f"{intrinsic}_{method}"] = template.render(
          name=method,
          data=tables_dict[mixin]["methods"][method],
          mixin=mixin,
          intrinsic=intrinsic,
          referenced_types=referenced_types,
        )

  # build pages for tables that were referenced as types
  for kind in referenced_types:
    if kind in tables_dict:
      # need to do temporary substitution for / in the page path
      print(f"Templating page FrameXML_types:{kind}...", file=sys.stderr)
      template = jinja.get_template("type.j2")
      pages[Path("FrameXML_types") / kind] = template.render(
        name=kind,
        data=tables_dict[kind],
      )

  # write pages to file
  for page, text in pages.items():
    # define the full (relative) path of the file to write to
    path = (PAGES_DIR / page).with_suffix(".txt")

    # ensure the directory for the path exists
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
      print(f"Writing page {page}...")
      f.write(text)

  # DEBUG:
  # used_types = set()
  # for kind in referenced_types:
  #   if kind in tables_dict:
  #     used_types.add(kind)
  # print("MISSING API PAGES:", referenced_types - used_types)
  # print(json.dumps({
  #   "tables": tables_dict,
  #   "intrinsics": intrinsics_dict,
  #   "templates": templates_dict,
  # }, indent=2, sort_keys=True))

if __name__ == "__main__":
  main()
