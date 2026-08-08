import sys
from pathlib import Path

from luaparser import ast, astnodes # not particularly fast

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

class Method:
  def __init__(self, name: str) -> None:
    self.name = name
    self.signature = []
    self.returns = []

  def __iter__(self):
    yield "name", self.name
    yield "signature", self.signature
    yield "returns", self.returns

  def add_signature(self, name: str, kind: str = None) -> None:
    self.signature.append({
      "name": name,
      "type": kind if kind is not None else "unknown",
    })

  def add_return(self, name: str, kind: str) -> None:
    self.returns.append({
      "name": name,
      "type": kind,
    })

class Table:
  def __init__(self, name: str) -> None:
    self.name = name
    self.inherits = []
    self.methods = {}
    self.fields = []

  def __iter__(self):
    yield "name", self.name
    yield "inherits", self.inherits
    yield "methods", {
      name: dict(method)
      for name, method in self.methods.items()
    }
    yield "fields", self.fields

    if hasattr(self, "comment"):
      yield "comment", self.comment

  def add_inheritance(self, name: str) -> None:
    self.inherits.append(name)

  def add_method(self, method: Method) -> None:
    self.methods[method.name] = method

  def add_field(self, name: str, value: str, kind: str|None, comment: str|None) -> None:
    self.fields.append({
      "name": name,
      "value": value,
      "type": kind if kind is not None else "unknown",
      "comment": comment,
    })

  def add_comment(self, comment: str) -> None:
    self.comment = comment

def type_guesser(table: str, method: str, token: str) -> str:
  token = token.lstrip("_")
  if METHOD_SIGNATURE_MAP.get(table, {}).get(method, {}).get(token):
    return METHOD_SIGNATURE_MAP[table][method][token]
  if token == "unitToken":
    return "UnitToken"
  if token in ("enabled", "disabled"):
    return "boolean"
  if token in ("index"):
    return "number"
  return "unknown"

def parse_method_args(table: Table, method: Method, args: astnodes.Name, body: astnodes.Block) -> None:
  for node in args:
    if isinstance(node, astnodes.Name):
      method.add_signature(node.id, type_guesser(table.name, method.name, node.id))
    elif isinstance(node, astnodes.Varargs):
      method.add_signature("...")
    else:
      raise RuntimeException(f"bad arg type for method '{method.name}'")

def parse_method_returns(table: Table, method: Method, body: astnodes.Block) -> None:
  returns = []

  for node in ast.walk(body):
    if isinstance(node, astnodes.Return) and len(node.values) > 0:
      for index, value in enumerate(node.values):
        if isinstance(value, astnodes.Call):
          # try to unwrap some returns that are from function calls
          if hasattr(value.func, "id") and value.func.id == "secretwrap":
            value = value.args[0]

        # try to assign names to return value
        name = None
        if isinstance(value, astnodes.Name):
          name = value.id
        elif isinstance(value, astnodes.Index):
          if hasattr(value, "idx") and hasattr(value.idx, "id"):
            name = value.idx.id
          elif hasattr(value, "id"):
            name = value.id
        elif method.name.startswith("Get"):
          name = method.name[3:4].lower() + method.name[4:]
        elif method.name.startswith("Is") or method.name.startswith("Has") or method.name.startswith("Should"):
          name = method.name[:1].lower() + method.name[1:]
          kind = "boolean" # this should always be the case

        # try to assign type of return value
        kind = None
        if isinstance(value, astnodes.FalseExpr) or isinstance(value, astnodes.TrueExpr):
          kind = "boolean"
        elif isinstance(value, astnodes.RelOp):
          kind = "boolean"
        elif isinstance(value, astnodes.LoOp):
          kind = "boolean"
        elif isinstance(value, astnodes.UnaryOp):
          kind = "number"
        elif isinstance(value, astnodes.Name):
          kind = type_guesser(table.name, method.name, value.id) #+ "-----1"
        elif isinstance(value, astnodes.Index):
          if hasattr(value, "idx") and hasattr(value.idx, "id"):
            kind = type_guesser(table.name, method.name, value.idx.id) #+ "-----2"
          elif hasattr(value, "id"):
            kind = type_guesser(table.name, method.name, value.id) #+ "-----3"
        # else:
        #   print(ast.to_pretty_str(value))

        if kind is None and name is not None and METHOD_SIGNATURE_MAP.get(table.name, {}).get(method.name, {}).get(name):
          kind = METHOD_SIGNATURE_MAP[table.name][method.name][name]

        returns.append({
          "name": name if name is not None else "unknown",
          "type": kind if kind is not None else "unknown",
        })

  for ret in returns:
    method.add_return(ret["name"], ret["type"])

def parse_table_method(table: Table, name: str, args: astnodes.Name, body: astnodes.Block) -> None:
  method: Method = Method(name)

  if len(args) > 0:
    parse_method_args(table, method, args, body)

  if len(body.body) > 0:
    parse_method_returns(table, method, body.body)

  table.add_method(method)

def parse_table_field(table: Table, field: astnodes.Field) -> None:
  name = None
  if hasattr(field.key, "id"):
    name = field.key.id
  elif hasattr(field.key, "idx"):
    if hasattr(field.key.value, "id"):
      name = f"{field.key.value.id}.{field.key.idx.id}"
    elif hasattr(field.key.value, "idx"):
      if hasattr(field.key.value.value, "id"):
        name = f"{field.key.value.value.id}.{field.key.value.idx.id}.{field.key.idx.id}"

  if name is None:
    # TODO: we should error here
    return

  value = None
  kind = None
  if isinstance(field.value, astnodes.Index):
    if hasattr(field.value, "idx"):
      if hasattr(field.value.value, "id"):
        value = f"{field.value.value.id}.{field.value.idx.id}"
        kind = field.value.value.id
      elif hasattr(field.value.value, "idx"):
        if hasattr(field.value.value.value, "id"):
          value = f"{field.value.value.value.id}.{field.value.value.idx.id}.{field.value.idx.id}"
          kind = f"{field.value.value.value.id}.{field.value.value.idx.id}"
  elif isinstance(field.value, astnodes.Call):
    if hasattr(field.value, "func"):
      if hasattr(field.value.func, "value") and field.value.func.value.id == "bit":
        value = "unknown"
        kind = "number"
      elif hasattr(field.value.func, "id") and field.value.func.id == "assertsafe":
        # blizzard is doing something wonky here
        value = field.value.args[0].id
        kind = "number" # it's really a constant but we know it refers to a number
  elif isinstance(field.value, astnodes.TrueExpr):
    value = "true"
    kind = "boolean"
  elif isinstance(field.value, astnodes.FalseExpr):
    value = "false"
    kind = "boolean"
  elif isinstance(field.value, astnodes.Number):
    value = field.value.n
    kind = "number"
  elif isinstance(field.value, astnodes.String):
    value = field.value.raw
    kind = "string"
  elif isinstance(field.value, astnodes.Nil):
    value = "nil"
    if "index" in name.casefold():
      kind = "number"
    elif "height" in name.casefold():
      kind = "number"
    elif "width" in name.casefold():
      kind = "number"
    elif name == "templateNames":
      kind = "string"
    elif name == "candidateFilters":
      kind = "table"
    elif name == "initializeFrame":
      kind = "function"
    # else:
    #   print('UNKNOWN FIELD TYPE', name)
  elif isinstance(field.value, astnodes.Name):
    value = field.value.id
    kind = "number" # it's really a constant but we know it refers to a number
  else:
    # unsupported field, we should throw an error tho
    # print(ast.to_pretty_str(field))
    return

  comment = None
  if hasattr(field, "comments"):
    comment = "\n".join([comment.s.lstrip("-- ") for comment in field.comments])

  if name is not None and value is not None:
    table.add_field(name, value, kind, comment)
  else:
    # TODO: we should error here
    # print(ast.to_pretty_str(field))
    pass

def parse_lua_tables(tables: dict[str, Table], file: Path) -> None:
  with open(file, "r", encoding="utf-8-sig") as f:
    tree = ast.parse(f.read())

  for node in ast.walk(tree.body.body):
    if isinstance(node, astnodes.Assign):
      if len(node.values) > 0:
        if isinstance(node.values[0], astnodes.Table):
          if hasattr(node.targets[0], "id"):
            name = node.targets[0].id
            if name not in tables:
              tables[name] = Table(name)

            # parse comments
            if hasattr(node, "comments"):
              tables[name].add_comment("\n".join([comment.s.lstrip("-- ") for comment in node.comments]))

            # parse fields in the table
            if hasattr(node.values[0], "fields") and len(node.values[0].fields) > 0 and not isinstance(node, astnodes.LocalAssign):
              for field in node.values[0].fields:
                parse_table_field(tables[name], field)
        elif isinstance(node.values[0], astnodes.Call) and hasattr(node.values[0].func, "id"):
          func = node.values[0].func.id
          if func == "CreateFromMixins" or func == "CreateFromMixinsPrivate" or func == "CreateProxyMixin":
            if hasattr(node.targets[0], "id"):
              name = node.targets[0].id
              if name not in tables:
                tables[name] = Table(name)

              # check for inheritance
              if hasattr(node.values[0], "args") and len(node.values[0].args) > 0:
                for arg in node.values[0].args:
                  if hasattr(arg, "id"):
                    tables[name].add_inheritance(arg.id)
                  elif hasattr(arg, "idx"):
                    # inherits from another table, we'll just reference it
                    tables[name].add_inheritance(f"{arg.value.id}.{arg.idx.id}")
    elif isinstance(node, astnodes.Method) and hasattr(node.source, "id"):
      name = node.source.id
      if name not in tables:
        tables[name] = Table(name)

      parse_table_method(tables[name], node.name.id, node.args, node.body) # TODO: consider node.body.body instead?

def get_lua_tables(sources: list[Path]) -> dict[str, Table]:
  tables: dict[str, Table] = {}

  for path in sources:
    for file in path.rglob("*.lua"):
      if INVALID_PATHS.intersection(file.parts):
        continue

      print(f"Parsing {Path(*file.parts[3:])}...", file=sys.stderr)
      parse_lua_tables(tables, file)

  return tables

# custom mapping of method signature, since we can't scrape this info (reliably)
METHOD_SIGNATURE_MAP = {
  "CustomAuraButtonSharedMixin": {
    "AddDispelTypeTexture": {
      "texture": "Texture",
      "options": "Structure:CustomAuraButtonDispelTypeTextureOptions",
    },
    "AddPandemicRegion": {
      "region": "Region",
    },
    "GetApplicationBar": {
      "applicationBar": "StatusBar",
    },
    "GetApplicationCount": {
      "applicationCount": "FontString",
    },
    "GetAuraBorder": { # deprecated
      "auraBorder": "Texture",
    },
    "GetDispelTypeText": {
      "dispelTypeText": "FontString",
    },
    "GetDispelTypeTexture": {
      "dispelTypeTexture": "Texture",
    },
    "GetDurationBar": {
      "durationBar": "StatusBar",
    },
    "GetDurationCooldown": {
      "durationCooldown": "Cooldown",
    },
    "GetDurationText": {
      "durationText": "FontString",
    },
    "GetIcon": {
      "icon": "Texture",
    },
    "GetSpellName": {
      "spellName": "FontString",
    },
    "SetApplicationBar": {
      "statusBar": "StatusBar",
      "options": "Structure:CustomAuraButtonApplicationBarOptions",
    },
    "SetApplicationCount": {
      "fontString": "FontString",
      "options": "Structure:CustomAuraButtonApplicationCountOptions",
    },
    "SetAuraBorder": { # deprecated
      "texture": "Texture",
      "options": "Structure:CustomAuraButtonDispelTypeTextureOptions",
    },
    "SetDispelTypeText": {
      "fontString": "FontString",
      "options": "Structure:CustomAuraButtonDispelTypeTextOptions",
    },
    "SetDurationBar": {
      "statusBar": "StatusBar",
      "options": "Structure:CustomAuraButtonDurationBarOptions",
    },
    "SetDurationCooldown": {
      "cooldown": "Cooldown",
    },
    "SetDurationText": {
      "fontString": "FontString",
      "options": "Structure:CustomAuraButtonDurationTextOptions",
    },
    "SetIcon": {
      "texture": "Texture",
    },
    "SetSpellName": {
      "fontString": "FontString",
    },
  },
  "AuraButtonSharedMixin": {
    "GetTooltipAnchorPoint": {
      "tooltipAnchorPoint": "Type:TooltipAnchor",
      "tooltipOffsetX": "number",
      "tooltipOffsetY": "number",
    },
    "SetCancelAuraButtons": {
      "cancelAuraButtons": "string",
    },
    "SetHideTooltipInCombat": {
      "hideInCombat": "boolean",
    },
    "SetTooltipAnchorPoint": {
      "point": "Type:TooltipAnchor",
      "offsetX": "number",
      "offsetY": "number",
    },
  },
  "CustomAuraContainerSharedMixin": {
    "AddAuraGroup": {
      "groupKey": "string",
      "filterString": "Type:AuraFilters",
      "options": "FType:CustomAuraContainerGroupDefaultOptions",
    },
    "AddAuraSlot": {
      "slotKey": "string",
      "filterString": "Type:AuraFilters",
      "options": "FType:CustomAuraContainerSlotDefaultOptions",
    },
    "AddItemEnchantment": {
      "itemEnchantmentSlot": "Structure:AuraContainerItemEnchantmentSlot",
      "options": "Structure:CustomAuraContainerItemEnchantmentDefaultOptions",
    },
    "GetAuraGroupFrame": {
      "groupKey": "string",
      "frameIndex": "number",
      "auraFrame": "AuraButton",
    },
    "GetAuraGroupFrameCount": {
      "groupKey": "string",
      "auraFrameCount": "number",
    },
    "GetAuraProcessingPolicy": {
      "auraProcessingPolicy": "FType:CustomAuraContainerAuraProcessingPolicy",
    },
    "HasAuraGroup": {
      "groupKey": "string",
    },
    "SetAuraGroupCandidateFilters": {
      "groupKey": "string",
      "candidateFilters": "unknown", # TODO: we should create a custom page for this
    },
    "SetAuraGroupFilterString": {
      "groupKey": "string",
      "filterString": "Type:AuraFilters",
    },
    "SetAuraGroupLayout": {
      "groupKey": "string",
      "layoutOptions": "FType:CustomAuraContainerGroupLayoutDefaultOptions",
    },
    "SetAuraGroupMaxFrameCount": {
      "groupKey": "string",
      "maxFrameCount": "number",
    },
    "SetAuraGroupSortMethod": {
      "groupKey": "string",
      "sortMethod": "FType:AuraContainerSortMethod",
      "sortDirection": "FType:AuraContainerSortDirection",
    },
    "SetAuraProcessingPolicy": {
      "policy": "FType:CustomAuraContainerAuraProcessingPolicy",
      "options": "FType:CustomAuraContainerProcessAuraPolicyDefaultOptions",
    },
    "SetAuraSlotCandidateFilters": {
      "slotKey": "string",
      "candidateFilters": "unknown", # TODO: we should create a custom page for this
    },
    "SetAuraSlotFilterString": {
      "slotKey": "string",
      "filterString": "Type:AuraFilters",
    },
    "SetAuraSlotSortMethod": {
      "slotKey": "string",
      "sortMethod": "FType:AuraContainerSortMethod",
      "sortDirection": "FType:AuraContainerSortDirection",
    },
    "SetItemEnchantmentLayout": {
      "layoutOptions": "FType:CustomAuraContainerItemEnchantmentLayoutDefaultOptions",
    },
    "SetItemEnchantmentSortMethod": {
      "sortMethod": "FType:AuraContainerItemEnchantmentSortMethod",
      "sortDirection": "FType:AuraContainerSortDirection",
    },
  },
  "AuraContainerFlowLayoutSharedMixin": {
    "GetFlowLayoutAnchorPoint": {
      "flowLayoutAnchorPoint": "Page:FramePoint",
    },
    "GetFlowLayoutAxis": {
      "flowLayoutAxis": "FType:AnchorUtil.FlowLayoutAxis",
    },
    "GetFlowLayoutGrowthDirection": {
      "flowLayoutGrowthDirection": "FType:AnchorUtil.FlowDirection",
    },
    "GetFlowLayoutMaximumLineSize": {
      "flowLayoutMaximumLineSize": "number",
    },
    "GetFlowLayoutPadding": {
      "flowLayoutPadding": "number",
    },
    "SetFlowLayoutAnchorPoint": {
      "anchorPoint": "Page:FramePoint",
    },
    "SetFlowLayoutAxis": {
      "layoutAxis": "FType:AnchorUtil.FlowLayoutAxis",
    },
    "SetFlowLayoutGrowthDirection": {
      "horizontalDirection": "FType:AnchorUtil.FlowDirection",
      "verticalDirection": "FType:AnchorUtil.FlowDirection",
    },
    "SetFlowLayoutMaximumLineSize": {
      "maximumLineSize": "number",
    },
    "SetFlowLayoutPadding": {
      "left": "number",
      "right": "number",
      "top": "number",
      "bottom": "number",
    },
  },

  # TODO: for all the other non-AuraContainer intrinsic mixin methods
}
