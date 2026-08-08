import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final

XML_NAMESPACES: Final[dict[str, str]] = {
  "ns": "http://www.blizzard.com/wow/ui/"
}

INVALID_PATHS = {
  "WoWHack",
  "WoWLabs",
  "Vanilla",
  "TBC",
  "Wrath",
  "Cata",
  "Mists",
  "Classic",
}

class Template:
  def __init__(self, element: ET.Element, namespace: dict[str, str]) -> None:
    self.name: str = element.attrib.get("name")
    self.type: str = element.tag.replace(f"{{{namespace['ns']}}}", "")

    self.mixins: list[str] = []
    if mixins := element.attrib.get("mixin"):
      for mixin in [mixin.strip() for mixin in mixins.split(', ')]:
        self.mixins.append(mixin)
    for mixin in element.findall(".//ns:Mixin[@targetPartition='public']", namespace):
      if value := mixin.attrib.get("key"):
        self.mixins.append(value)

  def __iter__(self):
    yield "name", self.name
    yield "type", self.type
    yield "mixins", self.mixins

class Intrinsic:
  def __init__(self, element: ET.Element, namespace: dict[str, str]) -> None:
    self.name: str = element.attrib.get("name")
    self.type: str = element.tag.replace(f"{{{namespace['ns']}}}", "")

    self.mixins: list[str] = []
    if mixin := element.attrib.get("mixin"):
      self.mixins.append(mixin)
    for mixin in element.findall(".//ns:Mixin[@targetPartition='public']", namespace):
      if value := mixin.attrib.get("key"):
        self.mixins.append(value)

    self.aspects: list[str] = []
    for aspect in element.findall(".//ns:ForbiddenAspect", namespace):
      if value := aspect.attrib.get("aspect"):
        self.aspects.append(value)

  def __iter__(self):
    yield "name", self.name
    yield "type", self.type
    yield "mixins", self.mixins
    yield "aspects", self.aspects

def get_xml_intrinsics(source: Path) -> tuple[list[Intrinsic], list[Path]]:
  intrinsics: list[Intrinsic] = []
  paths: list[Path] = []

  for file in source.rglob("*.xml"):
    if INVALID_PATHS.intersection(file.parts):
      continue

    print(f"Parsing {Path(*file.parts[3:])}...", file=sys.stderr)

    try:
      tree: ET.ElementTree = ET.parse(file)
      root: ET.Element = tree.getroot()

      for element in root.findall(".//ns:*", XML_NAMESPACES):
        if element.attrib.get("intrinsic") == "true":
          intrinsics.append(Intrinsic(element, XML_NAMESPACES))
          paths.append(file)
    except ET.ParseError as e:
      raise RuntimeError(f"Malformed XML error in {file.name}: {e}") from e

  return intrinsics, paths

def get_xml_templates(sources: list[Path]) -> list[Template]:
  templates: list[Template] = []

  for path in sources:
    for file in path.rglob("*.xml"):
      if INVALID_PATHS.intersection(file.parts):
        continue

      print(f"Parsing {Path(*file.parts[3:])}...", file=sys.stderr)

      try:
        tree: ET.ElementTree = ET.parse(file)
        root: ET.Element = tree.getroot()

        for element in root.findall(".//ns:*", XML_NAMESPACES):
          if element.attrib.get("virtual") == "true":
            templates.append(Template(element, XML_NAMESPACES))
      except ET.ParseError as e:
        raise RuntimeError(f"Malformed XML error in {file.name}: {e}") from e

  return templates
