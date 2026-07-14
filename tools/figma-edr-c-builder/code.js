const RUN_ID = "edr-c-ux-20260713";

const FALLBACK = {
  "color/background/page": { r: 0.063, g: 0.071, b: 0.082 },
  "color/background/shell": { r: 0.051, g: 0.059, b: 0.071 },
  "color/surface/panel": { r: 0.090, g: 0.110, b: 0.133 },
  "color/surface/raised": { r: 0.125, g: 0.153, b: 0.200 },
  "color/surface/inset": { r: 0.067, g: 0.086, b: 0.110 },
  "color/surface/hover": { r: 0.106, g: 0.133, b: 0.173 },
  "color/border/default": { r: 0.196, g: 0.227, b: 0.275 },
  "color/border/subtle": { r: 0.153, g: 0.180, b: 0.220 },
  "color/text/primary": { r: 0.933, g: 0.949, b: 0.969 },
  "color/text/secondary": { r: 0.604, g: 0.659, b: 0.729 },
  "color/text/tertiary": { r: 0.455, g: 0.510, b: 0.588 },
  "color/status/danger": { r: 0.949, g: 0.286, b: 0.361 },
  "color/status/warning": { r: 1.000, g: 0.702, b: 0.341 },
  "color/status/success": { r: 0.451, g: 0.749, b: 0.412 },
  "color/status/info": { r: 0.341, g: 0.580, b: 0.949 },
  "color/status/accent": { r: 0.337, g: 0.816, b: 0.902 }
};

const TYPE = {
  micro: { size: 11, style: "Extra Bold", line: 14, variable: "font/micro" },
  caption: { size: 12, style: "Medium", line: 17, variable: "font/caption" },
  bodySm: { size: 13, style: "Medium", line: 19, variable: "font/body-sm" },
  body: { size: 14, style: "Regular", line: 22, variable: "font/body" },
  titleSm: { size: 15, style: "Bold", line: 20, variable: "font/title-sm" },
  titleMd: { size: 16, style: "Extra Bold", line: 21, variable: "font/title-md" },
  titleLg: { size: 18, style: "Extra Bold", line: 24, variable: "font/title-lg" },
  displaySm: { size: 22, style: "Extra Bold", line: 27, variable: "font/display-sm" },
  displayMd: { size: 28, style: "Black", line: 31, variable: "font/display-md" },
  displayLg: { size: 34, style: "Black", line: 38, variable: "font/display-lg" },
  hero: { size: 64, style: "Black", line: 66, variable: null },
  heroSm: { size: 48, style: "Black", line: 52, variable: null }
};

let colorVars = {};
let floatVars = {};

function tag(node, key, phase) {
  node.setSharedPluginData("dsb", "run_id", RUN_ID);
  node.setSharedPluginData("dsb", "key", key);
  node.setSharedPluginData("dsb", "phase", phase || "phase4");
}

function boundPaint(name, alpha) {
  const base = FALLBACK[name] || { r: 0.5, g: 0.5, b: 0.5 };
  const paint = { type: "SOLID", color: base, opacity: alpha == null ? 1 : alpha };
  const variable = colorVars[name];
  return variable ? figma.variables.setBoundVariableForPaint(paint, "color", variable) : paint;
}

function setRadius(node, variableName, value) {
  node.cornerRadius = value;
  const variable = floatVars[variableName];
  if (variable && node.setBoundVariable) {
    node.setBoundVariable("topLeftRadius", variable);
    node.setBoundVariable("topRightRadius", variable);
    node.setBoundVariable("bottomLeftRadius", variable);
    node.setBoundVariable("bottomRightRadius", variable);
  }
}

function fixedFrame(parent, name, width, height, mode, fillName) {
  const node = figma.createFrame();
  node.name = name;
  node.resize(width, height);
  node.layoutMode = mode || "NONE";
  if (node.layoutMode !== "NONE") {
    node.primaryAxisSizingMode = "FIXED";
    node.counterAxisSizingMode = "FIXED";
  }
  node.fills = fillName ? [boundPaint(fillName)] : [];
  node.clipsContent = false;
  parent.appendChild(node);
  return node;
}

function vFrame(parent, name, width, fillName, gap, padding) {
  const node = figma.createFrame();
  node.name = name;
  node.resize(width, 10);
  node.layoutMode = "VERTICAL";
  node.primaryAxisSizingMode = "AUTO";
  node.counterAxisSizingMode = "FIXED";
  node.itemSpacing = gap == null ? 16 : gap;
  const p = padding || 0;
  node.paddingTop = p;
  node.paddingBottom = p;
  node.paddingLeft = p;
  node.paddingRight = p;
  node.fills = fillName ? [boundPaint(fillName)] : [];
  node.clipsContent = false;
  parent.appendChild(node);
  return node;
}

function hFrame(parent, name, width, height, fillName, gap, padding) {
  const node = figma.createFrame();
  node.name = name;
  node.resize(width, height);
  node.layoutMode = "HORIZONTAL";
  node.primaryAxisSizingMode = "FIXED";
  node.counterAxisSizingMode = "FIXED";
  node.itemSpacing = gap == null ? 12 : gap;
  const p = padding || 0;
  node.paddingTop = p;
  node.paddingBottom = p;
  node.paddingLeft = p;
  node.paddingRight = p;
  node.fills = fillName ? [boundPaint(fillName)] : [];
  node.clipsContent = false;
  parent.appendChild(node);
  return node;
}

function text(parent, value, preset, colorName, width, align) {
  const spec = TYPE[preset] || TYPE.body;
  const node = figma.createText();
  node.name = "text/" + value.slice(0, 28);
  node.fontName = { family: "Inter", style: spec.style };
  node.characters = value;
  node.fontSize = spec.size;
  node.lineHeight = { unit: "PIXELS", value: spec.line };
  node.fills = [boundPaint(colorName || "color/text/primary")];
  node.textAlignHorizontal = align || "LEFT";
  if (width) {
    node.resize(width, spec.line);
    node.textAutoResize = "HEIGHT";
  }
  parent.appendChild(node);
  const variable = spec.variable && floatVars[spec.variable];
  if (variable && node.setBoundVariable) node.setBoundVariable("fontSize", variable);
  return node;
}

function divider(parent, width) {
  const node = figma.createRectangle();
  node.name = "Divider";
  node.resize(width, 1);
  node.fills = [boundPaint("color/border/subtle")];
  parent.appendChild(node);
  return node;
}

function addStroke(node, colorName, weight) {
  node.strokes = [boundPaint(colorName || "color/border/default")];
  node.strokeWeight = weight || 1;
}

function pill(parent, label, tone, width) {
  const toneMap = {
    neutral: "color/text/secondary",
    info: "color/status/info",
    success: "color/status/success",
    warning: "color/status/warning",
    danger: "color/status/danger",
    accent: "color/status/accent"
  };
  const colorName = toneMap[tone] || toneMap.neutral;
  const node = fixedFrame(parent, "Status / " + label, width || Math.max(70, label.length * 7 + 24), 28, "HORIZONTAL", "color/surface/inset");
  node.primaryAxisAlignItems = "CENTER";
  node.counterAxisAlignItems = "CENTER";
  node.paddingLeft = 10;
  node.paddingRight = 10;
  node.itemSpacing = 6;
  setRadius(node, "radius/pill", 999);
  addStroke(node, colorName, 1);
  const dot = figma.createEllipse();
  dot.resize(7, 7);
  dot.fills = [boundPaint(colorName)];
  node.appendChild(dot);
  text(node, label, "micro", colorName);
  return node;
}

function smallButton(parent, label, style, width) {
  const fill = style === "primary" ? "color/status/info" : style === "danger" ? "color/status/danger" : "color/surface/raised";
  const node = fixedFrame(parent, "Button / " + label, width || 116, 36, "HORIZONTAL", fill);
  node.primaryAxisAlignItems = "CENTER";
  node.counterAxisAlignItems = "CENTER";
  node.paddingLeft = 14;
  node.paddingRight = 14;
  setRadius(node, "radius/control", 4);
  if (style !== "primary" && style !== "danger") addStroke(node, "color/border/default", 1);
  text(node, label, "bodySm", "color/text/primary");
  return node;
}

function inputField(parent, label, value, width, state) {
  const wrap = vFrame(parent, "Field / " + label, width, null, 7, 0);
  text(wrap, label.toUpperCase(), "micro", state === "error" ? "color/status/danger" : "color/text/tertiary");
  const field = fixedFrame(wrap, "control", width, 42, "HORIZONTAL", "color/surface/inset");
  field.paddingLeft = 12;
  field.paddingRight = 12;
  field.counterAxisAlignItems = "CENTER";
  setRadius(field, "radius/control", 4);
  addStroke(field, state === "error" ? "color/status/danger" : state === "focus" ? "color/status/info" : "color/border/default", 1);
  text(field, value, "bodySm", value.indexOf("Select") === 0 ? "color/text/tertiary" : "color/text/primary", width - 28);
  return wrap;
}

function sectionTitle(parent, eyebrow, titleValue, description) {
  text(parent, eyebrow.toUpperCase(), "micro", "color/status/accent");
  text(parent, titleValue, "displayLg", "color/text/primary");
  if (description) text(parent, description, "body", "color/text/secondary", 1180);
}

function panel(parent, titleValue, width, height, subtitle) {
  const node = fixedFrame(parent, "Panel / " + titleValue, width, height, "VERTICAL", "color/surface/panel");
  node.paddingTop = 16;
  node.paddingBottom = 16;
  node.paddingLeft = 16;
  node.paddingRight = 16;
  node.itemSpacing = 12;
  setRadius(node, "radius/panel", 6);
  addStroke(node, "color/border/default", 1);
  const head = hFrame(node, "Panel Header", width - 32, 24, null, 8, 0);
  head.counterAxisAlignItems = "CENTER";
  text(head, titleValue, "titleSm", "color/text/primary", subtitle ? width - 210 : width - 40);
  if (subtitle) text(head, subtitle, "caption", "color/text/tertiary", 150, "RIGHT");
  return node;
}

function metricCard(parent, label, value, tone, width) {
  const node = fixedFrame(parent, "KPI / " + label, width, 96, "VERTICAL", "color/surface/panel");
  node.paddingTop = 14;
  node.paddingBottom = 14;
  node.paddingLeft = 14;
  node.paddingRight = 14;
  node.itemSpacing = 6;
  setRadius(node, "radius/panel", 6);
  addStroke(node, "color/border/default", 1);
  text(node, label.toUpperCase(), "micro", "color/text/tertiary", width - 28);
  text(node, value, "displaySm", tone || "color/text/primary");
  return node;
}

function barRow(parent, label, value, max, tone, width) {
  const row = hFrame(parent, "Bar / " + label, width, 28, null, 10, 0);
  row.counterAxisAlignItems = "CENTER";
  text(row, label, "caption", "color/text/secondary", 110);
  const track = fixedFrame(row, "track", width - 180, 7, "NONE", "color/surface/inset");
  setRadius(track, "radius/pill", 999);
  const fill = figma.createRectangle();
  fill.name = "value";
  fill.resize(Math.max(6, (width - 180) * value / max), 7);
  fill.fills = [boundPaint(tone || "color/status/info")];
  fill.cornerRadius = 999;
  track.appendChild(fill);
  text(row, String(value), "caption", "color/text/primary", 40, "RIGHT");
  return row;
}

function dataTable(parent, headers, rows, widths, width) {
  const totalWidth = width || widths.reduce(function(a, b) { return a + b; }, 0);
  const table = fixedFrame(parent, "Data Table", totalWidth, 42 * (rows.length + 1), "VERTICAL", "color/surface/panel");
  setRadius(table, "radius/panel", 6);
  addStroke(table, "color/border/default", 1);
  function tableRow(values, header, index) {
    const row = fixedFrame(table, header ? "Header" : "Row " + (index + 1), totalWidth - 2, 42, "HORIZONTAL", header ? "color/surface/raised" : "color/surface/panel");
    row.counterAxisAlignItems = "CENTER";
    values.forEach(function(value, i) {
      const cell = fixedFrame(row, "Cell / " + headers[i], widths[i], 42, "HORIZONTAL", null);
      cell.paddingLeft = 12;
      cell.paddingRight = 10;
      cell.counterAxisAlignItems = "CENTER";
      text(cell, String(value), header ? "micro" : "caption", header ? "color/text/tertiary" : "color/text/primary", widths[i] - 22);
    });
    if (!header) addStroke(row, "color/border/subtle", 0.5);
  }
  tableRow(headers, true, 0);
  rows.forEach(function(row, i) { tableRow(row, false, i); });
  return table;
}

function cleanupPage(page) {
  page.children.slice().forEach(function(node) {
    if (node.getSharedPluginData && node.getSharedPluginData("dsb", "run_id") === RUN_ID) node.remove();
  });
}

function swatchCard(parent, variable, width) {
  const card = fixedFrame(parent, "Swatch / " + variable.name, width, 118, "VERTICAL", "color/surface/panel");
  card.paddingTop = 10;
  card.paddingBottom = 10;
  card.paddingLeft = 10;
  card.paddingRight = 10;
  card.itemSpacing = 8;
  setRadius(card, "radius/panel", 6);
  addStroke(card, "color/border/default", 1);
  const rect = figma.createRectangle();
  rect.name = "Variable Fill";
  rect.resize(width - 20, 58);
  rect.cornerRadius = 4;
  rect.fills = [figma.variables.setBoundVariableForPaint({ type: "SOLID", color: { r: 0.5, g: 0.5, b: 0.5 } }, "color", variable)];
  card.appendChild(rect);
  text(card, variable.name, "micro", "color/text/primary", width - 20);
  const syntax = variable.codeSyntax && variable.codeSyntax.WEB ? variable.codeSyntax.WEB : "—";
  text(card, syntax, "caption", "color/text/tertiary", width - 20);
  return card;
}

function buildCoverAndFoundations(page) {
  const cover = fixedFrame(page, "Cover / EDR_C Dashboard UX", 1440, 900, "VERTICAL", "color/background/page");
  cover.x = 0;
  cover.y = 0;
  cover.paddingTop = 88;
  cover.paddingBottom = 76;
  cover.paddingLeft = 96;
  cover.paddingRight = 96;
  cover.itemSpacing = 22;
  tag(cover, "cover", "phase2");
  const accent = fixedFrame(cover, "Accent", 1248, 6, "NONE", "color/status/accent");
  setRadius(accent, "radius/pill", 999);
  text(cover, "EDR_C · SECURITY OPERATIONS PRODUCT UX", "micro", "color/status/accent");
  const hero = text(cover, "Dashboard UX\nWireframes", "hero", "color/text/primary", 1120);
  hero.lineHeight = { unit: "PIXELS", value: 68 };
  text(cover, "Implemented frontend, reusable UI foundations, operational states, responsive behavior, and future investigation workflows.", "titleLg", "color/text/secondary", 1080);
  const spacer = fixedFrame(cover, "Spacer", 1248, 245, "NONE", null);
  const chips = hFrame(cover, "Cover Metadata", 1248, 92, null, 12, 0);
  [
    ["SOURCE", "React frontend"],
    ["MODE", "Dark only"],
    ["BASELINE", "1440 desktop"],
    ["UPDATED", "2026-07-13"]
  ].forEach(function(item) {
    const card = fixedFrame(chips, "Meta / " + item[0], 303, 92, "VERTICAL", "color/surface/panel");
    card.paddingTop = 16;
    card.paddingLeft = 16;
    card.itemSpacing = 8;
    setRadius(card, "radius/panel", 6);
    addStroke(card, "color/border/default", 1);
    text(card, item[0], "micro", "color/text/tertiary");
    text(card, item[1], "titleSm", "color/text/primary");
  });

  const guide = fixedFrame(page, "Getting Started / EDR_C", 1440, 900, "VERTICAL", "color/background/page");
  guide.x = 1600;
  guide.y = 0;
  guide.paddingTop = 72;
  guide.paddingBottom = 72;
  guide.paddingLeft = 80;
  guide.paddingRight = 80;
  guide.itemSpacing = 24;
  tag(guide, "getting-started", "phase2");
  sectionTitle(guide, "File map", "Getting Started", "Three Starter-plan pages, organized as wide documentation canvases. Implemented and future UX remain visually distinct.");
  const cards = hFrame(guide, "Guide Cards", 1280, 430, null, 20, 0);
  [
    ["01", "Foundations", "Variables and styles mirror frontend/src/styles.css."],
    ["02", "Components", "Reusable buttons, fields, pills, KPI, panels, navigation, tables, and states."],
    ["03", "Current Screens", "Login, Overview, list/detail routes, Operations, and Archive."],
    ["04", "UX States", "Loading, Empty, Error, Stale, and Forbidden states."],
    ["05", "Future Concepts", "Clearly marked API contract needed before implementation."]
  ].forEach(function(item) {
    const card = fixedFrame(cards, "Guide / " + item[1], 240, 430, "VERTICAL", "color/surface/panel");
    card.paddingTop = 20;
    card.paddingBottom = 20;
    card.paddingLeft = 20;
    card.paddingRight = 20;
    card.itemSpacing = 14;
    setRadius(card, "radius/panel", 6);
    addStroke(card, "color/border/default", 1);
    text(card, item[0], "displayMd", "color/status/info");
    text(card, item[1], "titleMd", "color/text/primary", 200);
    text(card, item[2], "bodySm", "color/text/secondary", 200);
  });
  const source = hFrame(guide, "Source of Truth", 1280, 72, "color/surface/inset", 16, 20);
  source.counterAxisAlignItems = "CENTER";
  setRadius(source, "radius/panel", 6);
  addStroke(source, "color/status/accent", 1);
  text(source, "SOURCE OF TRUTH", "micro", "color/status/accent");
  text(source, "Current UI: frontend/src/App.tsx + frontend/src/styles.css  ·  Future UX: API contract needed badge", "bodySm", "color/text/primary", 1000);

  const foundations = vFrame(page, "Foundations / EDR_C", 1440, "color/background/page", 64, 80);
  foundations.x = 3200;
  foundations.y = 0;
  tag(foundations, "foundations", "phase2");
  sectionTitle(foundations, "Design tokens", "Foundations", "Dark-only operational UI tokens. Components should use semantic variables; raw variables document the code source.");

  const allColors = Object.values(colorVars);
  const raw = allColors.filter(function(v) { return v.name.indexOf("raw/") === 0; });
  const semantic = allColors.filter(function(v) { return v.name.indexOf("color/") === 0; });
  const colorsSection = vFrame(foundations, "Section / Colors", 1280, null, 18, 0);
  text(colorsSection, "Colors", "displayMd", "color/text/primary");
  text(colorsSection, "Primitive source values", "titleSm", "color/text/secondary");
  for (let rowIndex = 0; rowIndex < 2; rowIndex++) {
    const row = hFrame(colorsSection, "Primitive Row " + (rowIndex + 1), 1280, 118, null, 12, 0);
    raw.slice(rowIndex * 8, rowIndex * 8 + 8).forEach(function(v) { swatchCard(row, v, 149); });
  }
  text(colorsSection, "Semantic application tokens", "titleSm", "color/text/secondary");
  for (let rowIndex = 0; rowIndex < 2; rowIndex++) {
    const row = hFrame(colorsSection, "Semantic Row " + (rowIndex + 1), 1280, 118, null, 12, 0);
    semantic.slice(rowIndex * 8, rowIndex * 8 + 8).forEach(function(v) { swatchCard(row, v, 149); });
  }

  const typeSection = vFrame(foundations, "Section / Typography", 1280, null, 0, 0);
  text(typeSection, "Typography", "displayMd", "color/text/primary");
  Object.keys(TYPE).filter(function(k) { return TYPE[k].variable; }).forEach(function(key) {
    const spec = TYPE[key];
    const row = fixedFrame(typeSection, "Type Specimen / " + key, 1280, 82, "HORIZONTAL", null);
    row.counterAxisAlignItems = "CENTER";
    row.itemSpacing = 20;
    text(row, key, "micro", "color/text/tertiary", 150);
    text(row, "Security telemetry Aa 0123", key, "color/text/primary", 620);
    text(row, "Inter " + spec.style + " · " + spec.size + " / " + spec.line, "caption", "color/text/tertiary", 320);
    divider(typeSection, 1280);
  });

  const dimensionSection = vFrame(foundations, "Section / Dimensions", 1280, null, 20, 0);
  text(dimensionSection, "Spacing & Radius", "displayMd", "color/text/primary");
  const dimCols = hFrame(dimensionSection, "Dimension Columns", 1280, 560, null, 40, 0);
  const spacing = fixedFrame(dimCols, "Spacing Tokens", 740, 560, "VERTICAL", "color/surface/panel");
  spacing.paddingTop = 20;
  spacing.paddingBottom = 20;
  spacing.paddingLeft = 20;
  spacing.paddingRight = 20;
  spacing.itemSpacing = 10;
  setRadius(spacing, "radius/panel", 6);
  addStroke(spacing, "color/border/default", 1);
  text(spacing, "Spacing scale", "titleMd", "color/text/primary");
  Object.keys(floatVars).filter(function(name) { return name.indexOf("space/") === 0; }).sort(function(a, b) {
    return Number(a.split("/")[1]) - Number(b.split("/")[1]);
  }).forEach(function(name) {
    const variable = floatVars[name];
    const value = variable.valuesByMode[Object.keys(variable.valuesByMode)[0]];
    const row = hFrame(spacing, "Spacing / " + name, 700, 30, null, 12, 0);
    row.counterAxisAlignItems = "CENTER";
    const bar = figma.createRectangle();
    bar.name = name;
    bar.resize(Math.max(2, value * 8), 10);
    bar.fills = [boundPaint("color/status/info")];
    bar.cornerRadius = 3;
    bar.setBoundVariable("height", floatVars["space/5"] || variable);
    row.appendChild(bar);
    text(row, name + " · " + value + "px · " + (variable.codeSyntax.WEB || ""), "caption", "color/text/secondary", 420);
  });
  const radius = fixedFrame(dimCols, "Radius & Elevation", 500, 560, "VERTICAL", "color/surface/panel");
  radius.paddingTop = 20;
  radius.paddingBottom = 20;
  radius.paddingLeft = 20;
  radius.paddingRight = 20;
  radius.itemSpacing = 20;
  setRadius(radius, "radius/panel", 6);
  addStroke(radius, "color/border/default", 1);
  text(radius, "Radius & elevation", "titleMd", "color/text/primary");
  ["radius/control", "radius/panel", "radius/pill"].forEach(function(name) {
    const variable = floatVars[name];
    const value = variable.valuesByMode[Object.keys(variable.valuesByMode)[0]];
    const row = hFrame(radius, "Radius / " + name, 460, 92, null, 18, 0);
    row.counterAxisAlignItems = "CENTER";
    const sample = fixedFrame(row, "Sample", 72, 72, "NONE", "color/surface/raised");
    setRadius(sample, name, Math.min(value, 36));
    addStroke(sample, "color/status/accent", 1);
    text(row, name + "\n" + value + "px · " + variable.codeSyntax.WEB, "bodySm", "color/text/secondary", 320);
  });
  const effect = fixedFrame(radius, "Effect / Panel Inset", 460, 92, "VERTICAL", "color/surface/raised");
  effect.paddingTop = 16;
  effect.paddingLeft = 16;
  effect.itemSpacing = 8;
  setRadius(effect, "radius/panel", 6);
  effect.effects = [{ type: "INNER_SHADOW", color: { r: 1, g: 1, b: 1, a: 0.03 }, offset: { x: 0, y: 1 }, radius: 0, spread: 0, visible: true, blendMode: "NORMAL" }];
  text(effect, "Effect / Panel Inset", "titleSm", "color/text/primary");
  text(effect, "0 1px 0 rgba(255,255,255,.03)", "caption", "color/text/tertiary");

  return { cover: cover, guide: guide, foundations: foundations };
}

function componentSection(root, eyebrow, titleValue, description, height) {
  const section = fixedFrame(root, "Component Section / " + titleValue, 1280, height, "VERTICAL", "color/surface/panel");
  section.paddingTop = 24;
  section.paddingBottom = 24;
  section.paddingLeft = 24;
  section.paddingRight = 24;
  section.itemSpacing = 14;
  setRadius(section, "radius/panel", 6);
  addStroke(section, "color/border/default", 1);
  text(section, eyebrow.toUpperCase(), "micro", "color/status/accent");
  text(section, titleValue, "displaySm", "color/text/primary");
  text(section, description, "bodySm", "color/text/secondary", 1180);
  return section;
}

function gridComponentSet(components, parent, name, columns, cellWidth, cellHeight, description) {
  const set = figma.combineAsVariants(components, parent);
  set.name = name;
  set.description = description;
  set.fills = [boundPaint("color/surface/inset")];
  set.strokes = [boundPaint("color/border/subtle")];
  set.strokeWeight = 1;
  set.cornerRadius = 6;
  const padding = 20;
  components.forEach(function(child, index) {
    child.x = padding + (index % columns) * cellWidth;
    child.y = padding + Math.floor(index / columns) * cellHeight;
  });
  const rows = Math.ceil(components.length / columns);
  set.resizeWithoutConstraints(padding * 2 + columns * cellWidth - 16, padding * 2 + rows * cellHeight - 16);
  tag(set, "componentset/" + name.toLowerCase().replace(/\s+/g, "-"), "phase3");
  return set;
}

function bindSpacing(node, name, properties) {
  const variable = floatVars[name];
  if (!variable || !node.setBoundVariable) return;
  properties.forEach(function(prop) { node.setBoundVariable(prop, variable); });
}

function buildLibrary(page) {
  const root = vFrame(page, "EDR_C Component Library", 1440, "color/background/page", 28, 80);
  root.x = 0;
  root.y = 0;
  tag(root, "component-library", "phase3");
  sectionTitle(root, "Reusable UI", "Component Library", "Local Figma components aligned to the current React implementation. Related families share this Starter-plan page.");

  const statusSection = componentSection(root, "Tier 0", "Status Pill", "Compact operational status across alerts, incidents, endpoints, events, queues, and service health.", 250);
  const statusVariants = [];
  [
    ["Neutral", "color/text/secondary"],
    ["Info", "color/status/info"],
    ["Success", "color/status/success"],
    ["Warning", "color/status/warning"],
    ["Danger", "color/status/danger"]
  ].forEach(function(item) {
    const comp = figma.createComponent();
    comp.name = "Tone=" + item[0];
    comp.resize(126, 30);
    comp.layoutMode = "HORIZONTAL";
    comp.paddingLeft = 10;
    comp.paddingRight = 10;
    comp.itemSpacing = 6;
    comp.primaryAxisAlignItems = "CENTER";
    comp.counterAxisAlignItems = "CENTER";
    comp.fills = [boundPaint("color/surface/inset")];
    setRadius(comp, "radius/pill", 999);
    addStroke(comp, item[1], 1);
    const dot = figma.createEllipse();
    dot.resize(7, 7);
    dot.fills = [boundPaint(item[1])];
    comp.appendChild(dot);
    text(comp, item[0], "micro", item[1]);
    statusSection.appendChild(comp);
    statusVariants.push(comp);
  });
  const statusSet = gridComponentSet(statusVariants, statusSection, "Status Pill", 5, 145, 54, "Operational status label with five semantic tones.");

  const buttonSection = componentSection(root, "Tier 1", "Button", "Action hierarchy for primary, secondary, and ghost controls with small/medium and default/disabled variants.", 560);
  const buttonVariants = [];
  ["Small", "Medium"].forEach(function(size) {
    ["Primary", "Secondary", "Ghost"].forEach(function(style) {
      ["Default", "Disabled"].forEach(function(state) {
        const comp = figma.createComponent();
        comp.name = "Size=" + size + ", Style=" + style + ", State=" + state;
        comp.layoutMode = "HORIZONTAL";
        comp.primaryAxisSizingMode = "AUTO";
        comp.counterAxisSizingMode = "FIXED";
        comp.resize(130, size === "Small" ? 32 : 40);
        comp.primaryAxisAlignItems = "CENTER";
        comp.counterAxisAlignItems = "CENTER";
        const padVar = size === "Small" ? "space/6" : "space/8";
        bindSpacing(comp, padVar, ["paddingLeft", "paddingRight"]);
        comp.paddingLeft = size === "Small" ? 12 : 16;
        comp.paddingRight = size === "Small" ? 12 : 16;
        setRadius(comp, "radius/control", 4);
        const fill = style === "Primary" ? "color/status/info" : style === "Secondary" ? "color/surface/raised" : "color/surface/inset";
        comp.fills = [boundPaint(fill)];
        if (style !== "Primary") addStroke(comp, "color/border/default", 1);
        comp.opacity = state === "Disabled" ? 0.42 : 1;
        const label = text(comp, style + " action", size === "Small" ? "caption" : "bodySm", "color/text/primary");
        label.name = "label";
        buttonSection.appendChild(comp);
        buttonVariants.push(comp);
      });
    });
  });
  const buttonSet = gridComponentSet(buttonVariants, buttonSection, "Button", 4, 280, 72, "Action component. Use Primary once per view; destructive actions require explicit confirmation.");

  const fieldSection = componentSection(root, "Tier 1", "Field", "Text and select controls with default, focus, and error states.", 540);
  const fieldVariants = [];
  ["Text", "Select"].forEach(function(type) {
    ["Default", "Focus", "Error"].forEach(function(state) {
      const comp = figma.createComponent();
      comp.name = "Type=" + type + ", State=" + state;
      comp.resize(340, 74);
      comp.layoutMode = "VERTICAL";
      comp.primaryAxisSizingMode = "FIXED";
      comp.counterAxisSizingMode = "FIXED";
      comp.itemSpacing = 7;
      comp.fills = [];
      const label = text(comp, type.toUpperCase() + " FIELD", "micro", state === "Error" ? "color/status/danger" : "color/text/tertiary");
      label.name = "label";
      const control = fixedFrame(comp, "control", 340, 44, "HORIZONTAL", "color/surface/inset");
      control.paddingLeft = 12;
      control.paddingRight = 12;
      control.counterAxisAlignItems = "CENTER";
      setRadius(control, "radius/control", 4);
      addStroke(control, state === "Focus" ? "color/status/info" : state === "Error" ? "color/status/danger" : "color/border/default", 1);
      const value = text(control, type === "Select" ? "Select an option" : "Type a value", "bodySm", "color/text/secondary", 290);
      value.name = "value";
      fieldSection.appendChild(comp);
      fieldVariants.push(comp);
    });
  });
  const fieldSet = gridComponentSet(fieldVariants, fieldSection, "Field", 3, 380, 108, "Form control family for filter and response workflows.");

  const cardSection = componentSection(root, "Tier 2", "Operational Cards", "KPI, panel, navigation, table, and state building blocks used throughout product screens.", 1720);
  const atomsRow = hFrame(cardSection, "Cards Row", 1232, 220, null, 20, 0);
  const kpi = figma.createComponent();
  kpi.name = "KPI Card";
  kpi.resize(250, 118);
  kpi.layoutMode = "VERTICAL";
  kpi.paddingTop = 16;
  kpi.paddingBottom = 16;
  kpi.paddingLeft = 16;
  kpi.paddingRight = 16;
  kpi.itemSpacing = 8;
  kpi.fills = [boundPaint("color/surface/panel")];
  setRadius(kpi, "radius/panel", 6);
  addStroke(kpi, "color/border/default", 1);
  text(kpi, "OPEN ALERTS", "micro", "color/text/tertiary");
  text(kpi, "128", "displayMd", "color/status/danger");
  text(kpi, "+18 in last hour", "caption", "color/text/secondary");
  atomsRow.appendChild(kpi);
  tag(kpi, "component/kpi-card", "phase3");

  const panelComp = figma.createComponent();
  panelComp.name = "Panel";
  panelComp.resize(430, 188);
  panelComp.layoutMode = "VERTICAL";
  panelComp.paddingTop = 16;
  panelComp.paddingBottom = 16;
  panelComp.paddingLeft = 16;
  panelComp.paddingRight = 16;
  panelComp.itemSpacing = 14;
  panelComp.fills = [boundPaint("color/surface/panel")];
  setRadius(panelComp, "radius/panel", 6);
  addStroke(panelComp, "color/border/default", 1);
  text(panelComp, "Panel title", "titleSm", "color/text/primary");
  divider(panelComp, 398);
  text(panelComp, "Content slot · charts, definitions, queues, or guidance", "bodySm", "color/text/secondary", 398);
  atomsRow.appendChild(panelComp);
  tag(panelComp, "component/panel", "phase3");

  const tableComp = figma.createComponent();
  tableComp.name = "Table Shell";
  tableComp.resize(500, 188);
  tableComp.layoutMode = "VERTICAL";
  tableComp.fills = [boundPaint("color/surface/panel")];
  setRadius(tableComp, "radius/panel", 6);
  addStroke(tableComp, "color/border/default", 1);
  ["Header row", "Data row", "Data row", "Data row"].forEach(function(value, index) {
    const row = fixedFrame(tableComp, value + " " + index, 500, 46, "HORIZONTAL", index === 0 ? "color/surface/raised" : "color/surface/panel");
    row.paddingLeft = 14;
    row.counterAxisAlignItems = "CENTER";
    text(row, value, index === 0 ? "micro" : "caption", index === 0 ? "color/text/tertiary" : "color/text/primary");
  });
  atomsRow.appendChild(tableComp);
  tag(tableComp, "component/table-shell", "phase3");

  const navVariants = [];
  ["Default", "Active"].forEach(function(state) {
    const comp = figma.createComponent();
    comp.name = "State=" + state;
    comp.resize(220, 44);
    comp.layoutMode = "HORIZONTAL";
    comp.paddingLeft = 12;
    comp.paddingRight = 12;
    comp.itemSpacing = 10;
    comp.counterAxisAlignItems = "CENTER";
    comp.fills = [boundPaint(state === "Active" ? "color/surface/raised" : "color/background/shell")];
    setRadius(comp, "radius/control", 4);
    const icon = fixedFrame(comp, "icon", 20, 20, "HORIZONTAL", state === "Active" ? "color/status/info" : "color/surface/inset");
    icon.primaryAxisAlignItems = "CENTER";
    icon.counterAxisAlignItems = "CENTER";
    setRadius(icon, "radius/control", 4);
    text(icon, "O", "micro", "color/text/primary");
    text(comp, "Overview", "bodySm", state === "Active" ? "color/text/primary" : "color/text/secondary");
    cardSection.appendChild(comp);
    navVariants.push(comp);
  });
  const navSet = gridComponentSet(navVariants, cardSection, "Navigation Item", 2, 280, 70, "Compact rail and expanded drawer navigation states.");

  const stateVariants = [];
  [
    ["Loading", "Preparing telemetry", "color/status/info"],
    ["Empty", "No records in this scope", "color/text/secondary"],
    ["Error", "Data could not be loaded", "color/status/danger"],
    ["Stale", "Last successful sync is old", "color/status/warning"],
    ["Forbidden", "Insufficient role permission", "color/status/danger"]
  ].forEach(function(item) {
    const comp = figma.createComponent();
    comp.name = "State=" + item[0];
    comp.resize(220, 178);
    comp.layoutMode = "VERTICAL";
    comp.paddingTop = 18;
    comp.paddingBottom = 18;
    comp.paddingLeft = 18;
    comp.paddingRight = 18;
    comp.itemSpacing = 10;
    comp.primaryAxisAlignItems = "CENTER";
    comp.counterAxisAlignItems = "CENTER";
    comp.fills = [boundPaint("color/surface/inset")];
    setRadius(comp, "radius/panel", 6);
    addStroke(comp, item[2], 1);
    const mark = fixedFrame(comp, "State icon", 40, 40, "HORIZONTAL", "color/surface/raised");
    mark.primaryAxisAlignItems = "CENTER";
    mark.counterAxisAlignItems = "CENTER";
    setRadius(mark, "radius/pill", 999);
    text(mark, item[0].slice(0, 1), "titleMd", item[2]);
    text(comp, item[0], "titleMd", "color/text/primary");
    text(comp, item[1], "caption", "color/text/secondary", 184, "CENTER");
    cardSection.appendChild(comp);
    stateVariants.push(comp);
  });
  const stateSet = gridComponentSet(stateVariants, cardSection, "View State", 5, 238, 212, "First-class loading, empty, error, stale, and forbidden UI states.");

  return { root: root, statusSet: statusSet, buttonSet: buttonSet, fieldSet: fieldSet, kpi: kpi, panel: panelComp, table: tableComp, navSet: navSet, stateSet: stateSet };
}

function annotationBoard(page, name, category, x, y, width, height, future) {
  const outer = fixedFrame(page, name + " / Board", width, height + 60, "VERTICAL", "color/background/shell");
  outer.x = x;
  outer.y = y;
  tag(outer, "screen/" + name.toLowerCase().replace(/[^a-z0-9]+/g, "-"), future ? "phase4-future" : "phase4-current");
  const band = fixedFrame(outer, "Annotation", width, 60, "HORIZONTAL", "color/surface/inset");
  band.paddingLeft = 20;
  band.paddingRight = 20;
  band.itemSpacing = 12;
  band.counterAxisAlignItems = "CENTER";
  text(band, category.toUpperCase(), "micro", future ? "color/status/warning" : "color/status/accent");
  text(band, name, "titleMd", "color/text/primary", width - (future ? 430 : 260));
  if (future) pill(band, "API contract needed", "warning", 170);
  return { outer: outer, app: fixedFrame(outer, name, width, height, "NONE", "color/background/page") };
}

function appShell(app, titleValue, subtitle, active, width, height) {
  width = width || 1440;
  height = height || 900;
  app.layoutMode = "HORIZONTAL";
  app.primaryAxisSizingMode = "FIXED";
  app.counterAxisSizingMode = "FIXED";
  const railWidth = width < 600 ? 0 : 54;
  if (railWidth) {
    const rail = fixedFrame(app, "Navigation Rail", railWidth, height, "VERTICAL", "color/background/shell");
    rail.paddingTop = 14;
    rail.paddingBottom = 14;
    rail.itemSpacing = 12;
    rail.counterAxisAlignItems = "CENTER";
    text(rail, "E", "titleMd", "color/status/accent");
    ["Overview", "Alerts", "Incidents", "Endpoints", "Events", "Operations"].forEach(function(item) {
      const nav = fixedFrame(rail, "Nav / " + item, 34, 34, "HORIZONTAL", item === active ? "color/surface/raised" : "color/background/shell");
      nav.primaryAxisAlignItems = "CENTER";
      nav.counterAxisAlignItems = "CENTER";
      setRadius(nav, "radius/control", 4);
      if (item === active) addStroke(nav, "color/status/info", 1);
      text(nav, item.slice(0, 1), "micro", item === active ? "color/text/primary" : "color/text/tertiary");
    });
  }
  const body = fixedFrame(app, "App Body", width - railWidth, height, "VERTICAL", "color/background/page");
  const top = fixedFrame(body, "Top Bar", width - railWidth, 58, "HORIZONTAL", "color/background/shell");
  top.paddingLeft = 20;
  top.paddingRight = 20;
  top.itemSpacing = 14;
  top.counterAxisAlignItems = "CENTER";
  text(top, "EDR_C", "titleMd", "color/text/primary");
  text(top, "Security operations", "caption", "color/text/tertiary", width - railWidth - 420);
  pill(top, "LIVE", "success", 74);
  const avatar = fixedFrame(top, "User", 34, 34, "HORIZONTAL", "color/surface/raised");
  avatar.primaryAxisAlignItems = "CENTER";
  avatar.counterAxisAlignItems = "CENTER";
  setRadius(avatar, "radius/pill", 999);
  text(avatar, "AD", "micro", "color/text/primary");
  const content = fixedFrame(body, "Content", width - railWidth, height - 58, "VERTICAL", "color/background/page");
  content.paddingTop = width < 600 ? 16 : 24;
  content.paddingBottom = width < 600 ? 16 : 24;
  content.paddingLeft = width < 600 ? 16 : 24;
  content.paddingRight = width < 600 ? 16 : 24;
  content.itemSpacing = width < 600 ? 12 : 16;
  const header = fixedFrame(content, "Page Header", width - railWidth - (width < 600 ? 32 : 48), 60, "VERTICAL", null);
  header.itemSpacing = 5;
  text(header, titleValue, width < 600 ? "displaySm" : "displayMd", "color/text/primary");
  text(header, subtitle, "caption", "color/text/secondary", width - railWidth - 80);
  return content;
}

function filterBar(parent, width, items) {
  const row = fixedFrame(parent, "Global Filter Bar", width, 48, "HORIZONTAL", "color/surface/panel");
  row.paddingLeft = 10;
  row.paddingRight = 10;
  row.itemSpacing = 10;
  row.counterAxisAlignItems = "CENTER";
  setRadius(row, "radius/panel", 6);
  addStroke(row, "color/border/default", 1);
  items.forEach(function(item) {
    const chip = fixedFrame(row, "Filter / " + item, Math.min(210, Math.max(110, item.length * 8 + 30)), 30, "HORIZONTAL", "color/surface/inset");
    chip.paddingLeft = 10;
    chip.paddingRight = 10;
    chip.counterAxisAlignItems = "CENTER";
    setRadius(chip, "radius/control", 4);
    addStroke(chip, "color/border/subtle", 1);
    text(chip, item, "caption", "color/text/secondary");
  });
  return row;
}

function buildLogin(page, x, y) {
  const board = annotationBoard(page, "Login", "Current route · /login", x, y, 1440, 900, false);
  const app = board.app;
  const left = fixedFrame(app, "Brand Panel", 820, 900, "VERTICAL", "color/background/shell");
  left.x = 0;
  left.y = 0;
  left.paddingTop = 110;
  left.paddingLeft = 92;
  left.paddingRight = 92;
  left.itemSpacing = 24;
  text(left, "EDR_C · SECURITY OPERATIONS", "micro", "color/status/accent");
  text(left, "Know the signal.\nControl the response.", "heroSm", "color/text/primary", 650);
  text(left, "Unified visibility across endpoint health, alert severity, incident progress, and pipeline failures.", "titleLg", "color/text/secondary", 620);
  const signals = vFrame(left, "Signals", 620, null, 12, 0);
  ["Live endpoint telemetry", "Role-aware response guidance", "Failure queues and archive recovery"].forEach(function(value) {
    const row = hFrame(signals, "Signal", 620, 34, null, 10, 0);
    row.counterAxisAlignItems = "CENTER";
    const dot = figma.createEllipse();
    dot.resize(8, 8);
    dot.fills = [boundPaint("color/status/success")];
    row.appendChild(dot);
    text(row, value, "bodySm", "color/text/secondary");
  });
  const right = fixedFrame(app, "Login Surface", 620, 900, "VERTICAL", "color/background/page");
  right.x = 820;
  right.y = 0;
  right.paddingTop = 170;
  right.paddingLeft = 90;
  right.paddingRight = 90;
  right.itemSpacing = 18;
  text(right, "Sign in", "displayLg", "color/text/primary");
  text(right, "Use your assigned analyst or administrator account.", "bodySm", "color/text/secondary", 440);
  inputField(right, "Email", "analyst@example.com", 440, "default");
  inputField(right, "Password", "••••••••••••", 440, "default");
  const actions = hFrame(right, "Login Actions", 440, 42, null, 12, 0);
  smallButton(actions, "Sign in", "primary", 440);
  pill(right, "Authentication required", "info", 190);
}

function buildOverview(page, x, y) {
  const board = annotationBoard(page, "Overview", "Current route · /", x, y, 1440, 900, false);
  const content = appShell(board.app, "Overview", "Live posture and operational signals across the active scope.", "Overview", 1440, 900);
  filterBar(content, 1338, ["Last 24 hours", "All endpoints", "All severities", "Auto refresh · 30s"]);
  const state = hFrame(content, "EDR State", 1338, 42, "color/surface/inset", 10, 12);
  state.counterAxisAlignItems = "CENTER";
  pill(state, "EDR HEALTHY", "success", 126);
  text(state, "Telemetry is current · last sync 16 sec ago", "caption", "color/text/secondary", 900);
  const kpis = hFrame(content, "KPI Row", 1338, 96, null, 10, 0);
  [
    ["Open alerts", "128", "color/status/danger"],
    ["Critical", "14", "color/status/danger"],
    ["Open incidents", "27", "color/status/warning"],
    ["At-risk endpoints", "43", "color/status/warning"],
    ["Events / min", "6.2K", "color/status/info"],
    ["Pipeline failures", "8", "color/status/accent"]
  ].forEach(function(item) { metricCard(kpis, item[0], item[1], item[2], 214); });
  const row1 = hFrame(content, "Overview Panels 1", 1338, 240, null, 12, 0);
  const severity = panel(row1, "Alert severity", 432, 240, "last 24h");
  barRow(severity, "Critical", 14, 80, "color/status/danger", 398);
  barRow(severity, "High", 36, 80, "color/status/warning", 398);
  barRow(severity, "Medium", 58, 80, "color/status/info", 398);
  barRow(severity, "Low", 20, 80, "color/status/accent", 398);
  const volume = panel(row1, "Event volume", 444, 240, "6.2K/min");
  [42, 58, 35, 74, 62, 86, 55, 92, 64, 78, 68, 83].forEach(function(v, i) {
    const bar = figma.createRectangle();
    bar.name = "time " + i;
    bar.resize(21, Math.max(8, v));
    bar.x = 20 + i * 31;
    bar.y = 205 - v;
    bar.fills = [boundPaint("color/status/info", 0.78)];
    volume.appendChild(bar);
  });
  const endpoint = panel(row1, "Endpoint risk", 438, 240, "2,460 total");
  barRow(endpoint, "Healthy", 2310, 2460, "color/status/success", 404);
  barRow(endpoint, "At risk", 103, 2460, "color/status/warning", 404);
  barRow(endpoint, "Isolated", 4, 2460, "color/status/danger", 404);
  barRow(endpoint, "Offline", 43, 2460, "color/text/tertiary", 404);
  const row2 = hFrame(content, "Overview Panels 2", 1338, 174, null, 12, 0);
  const rules = panel(row2, "Top detection rules", 438, 174, "128 alerts");
  ["Suspicious PowerShell", "Credential dumping", "Unsigned binary"].forEach(function(v, i) {
    const r = hFrame(rules, "Rule", 404, 28, null, 8, 0);
    text(r, v, "caption", "color/text/secondary", 300);
    text(r, String([31, 19, 12][i]), "caption", "color/text/primary", 50, "RIGHT");
  });
  const mitre = panel(row2, "MITRE distribution", 438, 174, "7 tactics");
  ["Execution", "Credential Access", "Defense Evasion"].forEach(function(v, i) { barRow(mitre, v, [44, 27, 18][i], 50, "color/status/accent", 404); });
  const failures = panel(row2, "Failure distribution", 438, 174, "8 queued");
  ["Ingestion", "Normalization", "Archive"].forEach(function(v, i) { barRow(failures, v, [4, 3, 1][i], 8, "color/status/warning", 404); });
}

function buildListScreen(page, spec, x, y) {
  const board = annotationBoard(page, spec.title, "Current route · " + spec.route, x, y, 1440, 900, false);
  const content = appShell(board.app, spec.title, spec.subtitle, spec.active, 1440, 900);
  filterBar(content, 1338, spec.filters);
  const summary = hFrame(content, "List Summary", 1338, 42, "color/surface/inset", 12, 12);
  summary.counterAxisAlignItems = "CENTER";
  pill(summary, spec.summaryToneLabel, spec.summaryTone, 138);
  text(summary, spec.summary, "caption", "color/text/secondary", 950);
  smallButton(summary, "Export", "secondary", 102);
  dataTable(content, spec.headers, spec.rows, spec.widths, 1338);
  const pagination = hFrame(content, "Pagination", 1338, 40, null, 8, 0);
  pagination.counterAxisAlignItems = "CENTER";
  text(pagination, "Showing 1–5 of " + spec.total, "caption", "color/text/tertiary", 1120);
  smallButton(pagination, "Previous", "secondary", 90);
  smallButton(pagination, "Next", "secondary", 76);
}

function buildDetailScreen(page, spec, x, y) {
  const board = annotationBoard(page, spec.title, "Current route · " + spec.route, x, y, 1440, 900, false);
  const content = appShell(board.app, spec.title, spec.subtitle, spec.active, 1440, 900);
  const statusRow = hFrame(content, "Detail Status", 1338, 46, "color/surface/inset", 10, 12);
  statusRow.counterAxisAlignItems = "CENTER";
  pill(statusRow, spec.status, spec.tone, 126);
  text(statusRow, spec.id, "bodySm", "color/text/primary", 860);
  smallButton(statusRow, spec.action, spec.action === "Isolate endpoint" ? "danger" : "primary", 160);
  const defs = hFrame(content, "Definition Cards", 1338, 104, null, 10, 0);
  spec.metrics.forEach(function(item) { metricCard(defs, item[0], item[1], item[2], 214); });
  const row = hFrame(content, "Detail Panels", 1338, 284, null, 12, 0);
  const primary = panel(row, spec.primaryTitle, 660, 284, spec.primaryMeta);
  spec.primaryLines.forEach(function(line) {
    const r = hFrame(primary, "Line", 626, 31, null, 8, 0);
    text(r, line[0], "caption", "color/text/tertiary", 160);
    text(r, line[1], "bodySm", "color/text/primary", 440);
  });
  const secondary = panel(row, spec.secondaryTitle, 666, 284, spec.secondaryMeta);
  spec.secondaryLines.forEach(function(line) {
    const r = hFrame(secondary, "Line", 632, 31, null, 8, 0);
    text(r, line[0], "caption", "color/text/tertiary", 170);
    text(r, line[1], "bodySm", "color/text/primary", 440);
  });
  const bottom = hFrame(content, "Detail Bottom", 1338, 180, null, 12, 0);
  const guidance = panel(bottom, spec.bottomTitle, 888, 180, "analyst guidance");
  spec.guidance.forEach(function(line, i) {
    const r = hFrame(guidance, "Guidance " + i, 854, 28, null, 10, 0);
    const n = fixedFrame(r, "Step", 24, 24, "HORIZONTAL", "color/surface/raised");
    n.primaryAxisAlignItems = "CENTER";
    n.counterAxisAlignItems = "CENTER";
    setRadius(n, "radius/pill", 999);
    text(n, String(i + 1), "micro", "color/status/info");
    text(r, line, "caption", "color/text/secondary", 790);
  });
  const related = panel(bottom, "Related context", 438, 180, "linked records");
  spec.related.forEach(function(line) { text(related, line, "caption", "color/text/secondary", 404); });
}

function buildOperations(page, x, y) {
  const board = annotationBoard(page, "Operations", "Current route · /operations", x, y, 1440, 900, false);
  const content = appShell(board.app, "Operations", "Pipeline health, replay controls, and failure queues.", "Operations", 1440, 900);
  const kpis = hFrame(content, "Ops KPI", 1338, 96, null, 10, 0);
  [["Ingest rate", "6.2K/s", "color/status/info"], ["Success rate", "99.93%", "color/status/success"], ["DLQ", "8", "color/status/warning"], ["Lag p95", "1.4s", "color/status/accent"], ["Workers", "12/12", "color/status/success"], ["Archive jobs", "3", "color/status/info"]].forEach(function(i) { metricCard(kpis, i[0], i[1], i[2], 214); });
  const row = hFrame(content, "Ops Panels", 1338, 270, null, 12, 0);
  const pipeline = panel(row, "Pipeline stages", 438, 270, "live");
  [["Collect", "HEALTHY", "success"], ["Normalize", "HEALTHY", "success"], ["Detect", "DEGRADED", "warning"], ["Persist", "HEALTHY", "success"], ["Archive", "RUNNING", "info"]].forEach(function(i) {
    const r = hFrame(pipeline, "Stage", 404, 34, null, 8, 0);
    text(r, i[0], "caption", "color/text/secondary", 260);
    pill(r, i[1], i[2], 110);
  });
  const replay = panel(row, "Replay controls", 438, 270, "administrator");
  inputField(replay, "Queue", "failure-events", 404, "default");
  inputField(replay, "Batch size", "100", 404, "default");
  const a = hFrame(replay, "Replay Actions", 404, 40, null, 10, 0);
  smallButton(a, "Dry run", "secondary", 120);
  smallButton(a, "Replay batch", "primary", 140);
  const services = panel(row, "Service health", 438, 270, "6 services");
  [["API", 100, "color/status/success"], ["Worker", 96, "color/status/success"], ["Kafka", 88, "color/status/warning"], ["Postgres", 99, "color/status/success"], ["S3", 92, "color/status/accent"]].forEach(function(i) { barRow(services, i[0], i[1], 100, i[2], 404); });
  dataTable(content, ["TIME", "STAGE", "ERROR", "RETRY", "STATUS"], [
    ["14:42:08", "detect", "rule_timeout", "2/5", "queued"],
    ["14:38:51", "normalize", "schema_invalid", "1/5", "queued"],
    ["14:11:19", "archive", "object_missing", "5/5", "dead-letter"],
    ["13:52:04", "detect", "lookup_timeout", "3/5", "retrying"]
  ], [160, 180, 520, 170, 308], 1338);
}

function buildArchive(page, x, y) {
  const board = annotationBoard(page, "Operations · Archive", "Current route · /operations/archives", x, y, 1440, 900, false);
  const content = appShell(board.app, "Archive", "Search archived telemetry and manage restore requests.", "Operations", 1440, 900);
  const search = hFrame(content, "Archive Search", 1338, 126, "color/surface/panel", 12, 16);
  setRadius(search, "radius/panel", 6);
  addStroke(search, "color/border/default", 1);
  inputField(search, "Object key", "tenant-a/2026/07/12/events-0042.jsonl.gz", 620, "default");
  inputField(search, "Restore tier", "Select Standard", 280, "default");
  const actions = vFrame(search, "Actions", 360, null, 8, 0);
  text(actions, "RESTORE REQUEST", "micro", "color/text/tertiary");
  const row = hFrame(actions, "Buttons", 360, 40, null, 10, 0);
  smallButton(row, "Validate", "secondary", 120);
  smallButton(row, "Request restore", "primary", 180);
  const progress = panel(content, "Active restore", 1338, 138, "job rst_0182");
  const progressRow = hFrame(progress, "Progress", 1304, 42, null, 12, 0);
  pill(progressRow, "RESTORING", "info", 120);
  const track = fixedFrame(progressRow, "Track", 940, 10, "NONE", "color/surface/inset");
  const fill = figma.createRectangle();
  fill.resize(610, 10);
  fill.fills = [boundPaint("color/status/info")];
  fill.cornerRadius = 999;
  track.appendChild(fill);
  text(progressRow, "65%", "titleSm", "color/text/primary");
  text(progress, "Estimated availability: 18 minutes · request is idempotent and can be safely revisited.", "caption", "color/text/secondary", 1200);
  dataTable(content, ["CREATED", "OBJECT", "SIZE", "TIER", "STATUS", "EXPIRES"], [
    ["2026-07-13 14:21", "events-0042.jsonl.gz", "1.8 GB", "Standard", "restoring", "—"],
    ["2026-07-12 09:48", "events-0038.jsonl.gz", "2.1 GB", "Expedited", "available", "2026-07-17"],
    ["2026-07-11 19:02", "events-0032.jsonl.gz", "1.6 GB", "Standard", "expired", "2026-07-13"],
    ["2026-07-10 08:17", "events-0026.jsonl.gz", "2.4 GB", "Standard", "failed", "—"]
  ], [190, 420, 140, 160, 190, 238], 1338);
}

function stateBoard(page, x, y) {
  const board = annotationBoard(page, "UX States", "Required operational states", x, y, 1440, 900, false);
  const app = board.app;
  const root = fixedFrame(app, "States Canvas", 1440, 900, "VERTICAL", "color/background/page");
  root.paddingTop = 60;
  root.paddingLeft = 70;
  root.paddingRight = 70;
  root.itemSpacing = 28;
  sectionTitle(root, "Resilience", "First-class UX states", "Every data view must communicate whether it is loading, empty, failed, stale, or permission-limited.");
  const row = hFrame(root, "States", 1300, 420, null, 18, 0);
  [
    ["Loading", "Preparing telemetry", "Skeletons preserve the final table and card layout.", "color/status/info"],
    ["Empty", "No records found", "Explain the active scope and offer a safe next action.", "color/text/secondary"],
    ["Error", "Data could not be loaded", "Show retry and a stable incident reference.", "color/status/danger"],
    ["Stale", "Data may be outdated", "Retain the last good result with a visible timestamp.", "color/status/warning"],
    ["Forbidden", "Access restricted", "Name the required role without exposing protected data.", "color/status/danger"]
  ].forEach(function(item) {
    const card = fixedFrame(row, "State / " + item[0], 244, 420, "VERTICAL", "color/surface/panel");
    card.paddingTop = 24;
    card.paddingBottom = 24;
    card.paddingLeft = 20;
    card.paddingRight = 20;
    card.itemSpacing = 14;
    card.primaryAxisAlignItems = "CENTER";
    card.counterAxisAlignItems = "CENTER";
    setRadius(card, "radius/panel", 6);
    addStroke(card, item[3], 1);
    const icon = fixedFrame(card, "Icon", 52, 52, "HORIZONTAL", "color/surface/raised");
    icon.primaryAxisAlignItems = "CENTER";
    icon.counterAxisAlignItems = "CENTER";
    setRadius(icon, "radius/pill", 999);
    text(icon, item[0].slice(0, 1), "displaySm", item[3]);
    text(card, item[0], "titleMd", "color/text/primary");
    text(card, item[1], "bodySm", item[3], 204, "CENTER");
    text(card, item[2], "caption", "color/text/secondary", 204, "CENTER");
    if (item[0] === "Error") smallButton(card, "Retry", "primary", 120);
    if (item[0] === "Forbidden") smallButton(card, "Request access", "secondary", 150);
  });
}

function responsiveBoard(page, x, y) {
  const board = annotationBoard(page, "Responsive Overview", "Desktop · Tablet · Mobile", x, y, 1440, 900, false);
  const app = board.app;
  const root = fixedFrame(app, "Responsive Canvas", 1440, 900, "VERTICAL", "color/background/page");
  root.paddingTop = 44;
  root.paddingLeft = 44;
  root.paddingRight = 44;
  root.itemSpacing = 22;
  sectionTitle(root, "Responsive", "Same hierarchy, different density", "Desktop preserves the full rail and panel grid; tablet collapses density; mobile prioritizes status, filters, and the primary queue.");
  const row = hFrame(root, "Devices", 1352, 660, null, 24, 0);
  [
    ["Desktop 1440", 610, 560, true, 3],
    ["Tablet 1024", 430, 560, true, 2],
    ["Mobile 390", 264, 560, false, 1]
  ].forEach(function(item) {
    const device = fixedFrame(row, item[0], item[1], item[2], "VERTICAL", "color/background/page");
    device.itemSpacing = 10;
    setRadius(device, "radius/panel", 6);
    addStroke(device, "color/border/default", 1);
    const top = fixedFrame(device, "Top", item[1], 42, "HORIZONTAL", "color/background/shell");
    top.paddingLeft = 12;
    top.paddingRight = 12;
    top.counterAxisAlignItems = "CENTER";
    text(top, item[0], "micro", "color/text/secondary", item[1] - 24);
    const inner = fixedFrame(device, "Content", item[1], item[2] - 42, "VERTICAL", "color/background/page");
    inner.paddingTop = 14;
    inner.paddingLeft = 14;
    inner.paddingRight = 14;
    inner.itemSpacing = 10;
    text(inner, "Overview", "displaySm", "color/text/primary");
    filterBar(inner, item[1] - 28, item[4] === 1 ? ["24h"] : ["24h", "All endpoints"]);
    const k = hFrame(inner, "KPIs", item[1] - 28, 80, null, 8, 0);
    for (let i = 0; i < item[4]; i++) metricCard(k, ["Alerts", "Incidents", "Endpoints"][i], ["128", "27", "2.4K"][i], ["color/status/danger", "color/status/warning", "color/status/info"][i], (item[1] - 28 - 8 * (item[4] - 1)) / item[4]);
    const p = panel(inner, "Alert severity", item[1] - 28, item[4] === 1 ? 260 : 220, "live");
    barRow(p, "Critical", 14, 60, "color/status/danger", item[1] - 62);
    barRow(p, "High", 36, 60, "color/status/warning", item[1] - 62);
    barRow(p, "Medium", 58, 60, "color/status/info", item[1] - 62);
  });
}

function futureTriage(page, x, y) {
  const board = annotationBoard(page, "Analyst Alert Triage Workspace", "Future workflow", x, y, 1440, 900, true);
  const content = appShell(board.app, "Alert triage", "Keyboard-first queue review with evidence, decision, and next-alert continuity.", "Alerts", 1440, 900);
  const workspace = hFrame(content, "Triage Workspace", 1338, 650, null, 12, 0);
  const queue = panel(workspace, "Prioritized queue", 360, 650, "128 open");
  ["Credential dumping", "Suspicious PowerShell", "C2 beacon pattern", "Unsigned driver", "Impossible travel"].forEach(function(item, i) {
    const row = fixedFrame(queue, "Queue item", 326, 82, "VERTICAL", i === 0 ? "color/surface/raised" : "color/surface/inset");
    row.paddingTop = 10;
    row.paddingLeft = 10;
    row.itemSpacing = 6;
    setRadius(row, "radius/control", 4);
    text(row, item, "bodySm", "color/text/primary", 280);
    const meta = hFrame(row, "Meta", 300, 22, null, 8, 0);
    pill(meta, i < 2 ? "CRITICAL" : "HIGH", i < 2 ? "danger" : "warning", 88);
    text(meta, "2 min ago", "caption", "color/text/tertiary");
  });
  const evidence = panel(workspace, "Evidence", 610, 650, "alert alt_01982");
  pill(evidence, "HIGH CONFIDENCE", "danger", 142);
  text(evidence, "Credential dumping behavior detected on FIN-LT-042", "titleMd", "color/text/primary", 576);
  dataTable(evidence, ["TIME", "TYPE", "SIGNAL"], [
    ["14:41:03", "process", "rundll32 → lsass access"],
    ["14:41:05", "file", "sam.save created"],
    ["14:41:12", "network", "new outbound 185.220.101.4"],
    ["14:42:01", "identity", "service credential reuse"]
  ], [120, 120, 336], 576);
  const decision = panel(workspace, "Decision", 344, 650, "required");
  inputField(decision, "Disposition", "Select true positive", 310, "focus");
  inputField(decision, "Reason", "Credential access confirmed", 310, "default");
  inputField(decision, "Assign to", "SOC Tier 2", 310, "default");
  text(decision, "Response preview", "titleSm", "color/text/primary");
  ["Create incident", "Isolate endpoint", "Revoke active tokens"].forEach(function(v) {
    const r = hFrame(decision, "Response", 310, 30, null, 8, 0);
    const check = fixedFrame(r, "Check", 20, 20, "HORIZONTAL", "color/status/info");
    check.primaryAxisAlignItems = "CENTER";
    check.counterAxisAlignItems = "CENTER";
    setRadius(check, "radius/control", 4);
    text(check, "✓", "micro", "color/text/primary");
    text(r, v, "caption", "color/text/secondary");
  });
  smallButton(decision, "Submit & next alert", "primary", 310);
}

function futureTimeline(page, x, y) {
  const board = annotationBoard(page, "Incident Investigation Timeline", "Future workflow", x, y, 1440, 900, true);
  const content = appShell(board.app, "Incident investigation", "Correlate evidence, hypotheses, entities, and analyst decisions on one timeline.", "Incidents", 1440, 900);
  const header = hFrame(content, "Incident Header", 1338, 62, "color/surface/inset", 12, 12);
  header.counterAxisAlignItems = "CENTER";
  pill(header, "ACTIVE · P1", "danger", 116);
  text(header, "INC-2026-0713-0042 · Finance workstation compromise", "titleMd", "color/text/primary", 820);
  smallButton(header, "Add evidence", "secondary", 120);
  smallButton(header, "Contain", "danger", 100);
  const row = hFrame(content, "Investigation", 1338, 640, null, 12, 0);
  const entities = panel(row, "Entities", 300, 640, "7 linked");
  ["FIN-LT-042", "alice.kim", "185.220.101.4", "svc-finance", "rundll32.exe"].forEach(function(v, i) {
    const r = fixedFrame(entities, "Entity", 266, 54, "VERTICAL", i === 0 ? "color/surface/raised" : "color/surface/inset");
    r.paddingTop = 8;
    r.paddingLeft = 10;
    r.itemSpacing = 3;
    setRadius(r, "radius/control", 4);
    text(r, v, "bodySm", "color/text/primary");
    text(r, ["endpoint", "identity", "IP address", "service account", "process"][i], "caption", "color/text/tertiary");
  });
  const timeline = panel(row, "Investigation timeline", 730, 640, "UTC+09");
  [
    ["14:31", "Initial access", "Malicious document spawned PowerShell", "danger"],
    ["14:36", "Execution", "Encoded command downloaded second stage", "warning"],
    ["14:41", "Credential access", "LSASS access and SAM export", "danger"],
    ["14:42", "Command & control", "Beacon to known anonymizer exit", "warning"],
    ["14:48", "Analyst note", "Scope expanded to service credential", "info"]
  ].forEach(function(i) {
    const r = hFrame(timeline, "Timeline event", 696, 82, null, 12, 0);
    text(r, i[0], "caption", "color/text/tertiary", 54);
    const marker = fixedFrame(r, "Marker", 14, 14, "NONE", "color/status/" + i[3]);
    marker.cornerRadius = 999;
    const copy = vFrame(r, "Copy", 590, null, 4, 0);
    text(copy, i[1], "bodySm", "color/text/primary");
    text(copy, i[2], "caption", "color/text/secondary", 590);
  });
  const hypothesis = panel(row, "Hypotheses", 284, 640, "2 active");
  ["Credential theft enabled lateral movement", "C2 channel remains active on one host"].forEach(function(v, i) {
    const card = fixedFrame(hypothesis, "Hypothesis", 250, 132, "VERTICAL", "color/surface/inset");
    card.paddingTop = 12;
    card.paddingLeft = 12;
    card.paddingRight = 12;
    card.itemSpacing = 8;
    setRadius(card, "radius/control", 4);
    pill(card, i === 0 ? "LIKELY" : "INVESTIGATE", i === 0 ? "warning" : "info", 106);
    text(card, v, "caption", "color/text/secondary", 226);
  });
  smallButton(hypothesis, "Add hypothesis", "secondary", 250);
}

function futureEndpoint(page, x, y) {
  const board = annotationBoard(page, "Endpoint Investigation & Response", "Future workflow", x, y, 1440, 900, true);
  const content = appShell(board.app, "Endpoint investigation", "Evidence-led response with explicit blast radius and confirmation.", "Endpoints", 1440, 900);
  const host = hFrame(content, "Host", 1338, 76, "color/surface/inset", 12, 12);
  host.counterAxisAlignItems = "CENTER";
  pill(host, "AT RISK", "danger", 98);
  text(host, "FIN-LT-042 · Windows 11 · alice.kim · last seen 12 sec ago", "titleMd", "color/text/primary", 820);
  smallButton(host, "Collect triage", "secondary", 130);
  smallButton(host, "Isolate", "danger", 100);
  const row = hFrame(content, "Endpoint Workspace", 1338, 620, null, 12, 0);
  const tree = panel(row, "Process tree", 520, 620, "live snapshot");
  ["winword.exe", "  powershell.exe -enc ...", "    rundll32.exe comsvcs.dll", "      cmd.exe /c reg save", "    curl.exe 185.220.101.4"].forEach(function(v, i) {
    const r = fixedFrame(tree, "Process", 486, 46, "HORIZONTAL", i === 2 ? "color/surface/raised" : "color/surface/inset");
    r.paddingLeft = 10 + Math.max(0, v.indexOf(v.trim())) * 6;
    r.counterAxisAlignItems = "CENTER";
    text(r, v.trim(), "caption", i === 2 ? "color/status/danger" : "color/text/secondary", 430);
  });
  const telemetry = panel(row, "Endpoint telemetry", 440, 620, "last 15 min");
  [["CPU", 73, "color/status/warning"], ["Memory", 61, "color/status/info"], ["Network", 88, "color/status/danger"], ["Sensor", 96, "color/status/success"]].forEach(function(i) { barRow(telemetry, i[0], i[1], 100, i[2], 406); });
  divider(telemetry, 406);
  text(telemetry, "Recent indicators", "titleSm", "color/text/primary");
  ["sam.save", "185.220.101.4:443", "svc-finance token", "PowerShell encoded command"].forEach(function(v) { pill(telemetry, v, "warning", 220); });
  const response = panel(row, "Response plan", 354, 620, "confirmation required");
  inputField(response, "Action", "Isolate endpoint", 320, "focus");
  inputField(response, "Duration", "60 minutes", 320, "default");
  text(response, "Expected impact", "titleSm", "color/text/primary");
  ["User loses network access", "Sensor channel remains available", "4 active sessions terminated"].forEach(function(v) { text(response, "• " + v, "caption", "color/text/secondary", 320); });
  const warning = fixedFrame(response, "Confirmation", 320, 100, "VERTICAL", "color/surface/inset");
  warning.paddingTop = 12;
  warning.paddingLeft = 12;
  warning.itemSpacing = 6;
  setRadius(warning, "radius/control", 4);
  addStroke(warning, "color/status/danger", 1);
  text(warning, "Type FIN-LT-042 to confirm", "caption", "color/status/danger", 290);
  text(warning, "FIN-LT-042", "bodySm", "color/text/primary");
  smallButton(response, "Confirm isolation", "danger", 320);
}

function futureFailure(page, x, y) {
  const board = annotationBoard(page, "Failure Queue & Archive Restore", "Future workflow", x, y, 1440, 900, true);
  const content = appShell(board.app, "Failure recovery", "Diagnose, replay, archive, and restore with progress that survives navigation.", "Operations", 1440, 900);
  const flow = hFrame(content, "Recovery Flow", 1338, 72, "color/surface/inset", 10, 12);
  flow.counterAxisAlignItems = "CENTER";
  ["Select failures", "Validate replay", "Run batch", "Archive evidence", "Restore on demand"].forEach(function(v, i) {
    const step = fixedFrame(flow, "Step", 240, 42, "HORIZONTAL", i === 2 ? "color/surface/raised" : "color/surface/inset");
    step.paddingLeft = 10;
    step.itemSpacing = 8;
    step.counterAxisAlignItems = "CENTER";
    setRadius(step, "radius/control", 4);
    const n = fixedFrame(step, "Number", 24, 24, "HORIZONTAL", i < 3 ? "color/status/info" : "color/surface/raised");
    n.primaryAxisAlignItems = "CENTER";
    n.counterAxisAlignItems = "CENTER";
    setRadius(n, "radius/pill", 999);
    text(n, String(i + 1), "micro", "color/text/primary");
    text(step, v, "caption", "color/text/secondary", 180);
  });
  const row = hFrame(content, "Recovery", 1338, 580, null, 12, 0);
  const queue = panel(row, "Failure queue", 760, 580, "8 records");
  dataTable(queue, ["SELECT", "STAGE", "ERROR", "AGE", "RETRY"], [
    ["✓", "detect", "rule_timeout", "3m", "2/5"],
    ["✓", "normalize", "schema_invalid", "7m", "1/5"],
    ["—", "archive", "object_missing", "31m", "5/5"],
    ["✓", "detect", "lookup_timeout", "52m", "3/5"],
    ["—", "persist", "db_conflict", "1h", "4/5"]
  ], [90, 120, 280, 90, 112], 692);
  const side = vFrame(row, "Recovery Side", 566, null, 12, 0);
  const validate = panel(side, "Replay validation", 566, 272, "3 selected");
  [["Eligible", "3", "success"], ["Duplicate-safe", "3", "success"], ["Needs archive", "1", "warning"]].forEach(function(i) {
    const r = hFrame(validate, "Validation", 532, 32, null, 8, 0);
    text(r, i[0], "caption", "color/text/secondary", 330);
    pill(r, i[1], i[2], 60);
  });
  smallButton(validate, "Run validated batch", "primary", 200);
  const job = panel(side, "Persistent job progress", 566, 296, "job rpl_2048");
  pill(job, "RUNNING", "info", 100);
  const track = fixedFrame(job, "Progress", 532, 10, "NONE", "color/surface/inset");
  const fill = figma.createRectangle();
  fill.resize(378, 10);
  fill.fills = [boundPaint("color/status/info")];
  fill.cornerRadius = 999;
  track.appendChild(fill);
  text(job, "71% · 213 / 300 events · safe to leave this page", "bodySm", "color/text/primary", 500);
  const a = hFrame(job, "Job Actions", 532, 40, null, 10, 0);
  smallButton(a, "View log", "secondary", 110);
  smallButton(a, "Cancel job", "danger", 120);
}

function inventoryBoard(page, x, y) {
  const board = annotationBoard(page, "Screen Inventory & QA", "Coverage map", x, y, 1440, 900, false);
  const app = board.app;
  const root = fixedFrame(app, "Inventory", 1440, 900, "VERTICAL", "color/background/page");
  root.paddingTop = 56;
  root.paddingLeft = 70;
  root.paddingRight = 70;
  root.itemSpacing = 24;
  sectionTitle(root, "Coverage", "Wireframe inventory", "Every implemented route is represented, plus state, responsive, and future workflow boards.");
  const cols = hFrame(root, "Inventory Columns", 1300, 560, null, 24, 0);
  [
    ["CURRENT ROUTES", ["/login", "/", "/alerts", "/alerts/:alertId", "/incidents", "/incidents/:incidentId", "/endpoints", "/endpoints/:endpointId", "/events", "/events/:eventId", "/operations", "/operations/archives"], "success"],
    ["UX STATES", ["Loading", "Empty", "Error", "Stale", "Forbidden", "Desktop", "Tablet", "Mobile"], "info"],
    ["FUTURE · API CONTRACT", ["Alert triage workspace", "Incident investigation timeline", "Endpoint response confirmation", "Failure queue + restore progress"], "warning"]
  ].forEach(function(group) {
    const card = fixedFrame(cols, group[0], 417, 560, "VERTICAL", "color/surface/panel");
    card.paddingTop = 22;
    card.paddingBottom = 22;
    card.paddingLeft = 20;
    card.paddingRight = 20;
    card.itemSpacing = 12;
    setRadius(card, "radius/panel", 6);
    addStroke(card, group[2] === "warning" ? "color/status/warning" : "color/border/default", 1);
    text(card, group[0], "micro", group[2] === "warning" ? "color/status/warning" : "color/status/accent");
    group[1].forEach(function(value) {
      const r = hFrame(card, "Inventory row", 377, 28, null, 8, 0);
      const mark = figma.createEllipse();
      mark.resize(8, 8);
      mark.fills = [boundPaint("color/status/" + group[2])];
      r.appendChild(mark);
      text(r, value, "caption", "color/text/secondary", 340);
    });
  });
}

function buildProductUX(page) {
  const gapX = 1600;
  const gapY = 1080;
  buildLogin(page, 0, 0);
  buildOverview(page, gapX, 0);
  buildListScreen(page, {
    title: "Alerts", route: "/alerts", active: "Alerts", subtitle: "Prioritize and review detections in the active scope.",
    filters: ["Last 24 hours", "Severity · All", "Status · Open", "Search alerts"],
    summaryToneLabel: "128 OPEN", summaryTone: "danger", summary: "14 critical · 36 high · median age 18 minutes", total: "128",
    headers: ["SEVERITY", "STATUS", "ALERT", "ENDPOINT", "ASSIGNEE", "UPDATED"],
    rows: [
      ["CRITICAL", "open", "Credential dumping behavior", "FIN-LT-042", "Unassigned", "2m"],
      ["HIGH", "investigating", "Suspicious PowerShell chain", "HR-WS-118", "J. Park", "6m"],
      ["HIGH", "open", "C2 beacon pattern", "ENG-LT-077", "Unassigned", "11m"],
      ["MEDIUM", "triaged", "Unsigned binary execution", "OPS-WS-204", "S. Kim", "19m"],
      ["LOW", "closed", "Rare DNS query", "MKT-LT-016", "A. Lee", "28m"]
    ],
    widths: [150, 170, 390, 210, 190, 228]
  }, gapX * 2, 0);
  buildDetailScreen(page, {
    title: "Alert Detail", route: "/alerts/:alertId", active: "Alerts", subtitle: "Evidence, risk factors, and analyst response guidance.",
    status: "CRITICAL", tone: "danger", id: "ALT-2026-0713-01982 · Credential dumping behavior", action: "Create incident",
    metrics: [["Confidence", "96%", "color/status/danger"], ["Risk score", "92", "color/status/danger"], ["Events", "14", "color/status/info"], ["Endpoints", "1", "color/status/warning"], ["Users", "2", "color/status/warning"], ["Age", "18m", "color/status/accent"]],
    primaryTitle: "Detection summary", primaryMeta: "rule edr.credential.041", primaryLines: [["Title", "Credential dumping behavior"], ["Endpoint", "FIN-LT-042"], ["User", "alice.kim"], ["MITRE", "T1003 · OS Credential Dumping"], ["Process", "rundll32.exe → lsass.exe"], ["Source", "Endpoint sensor"]],
    secondaryTitle: "Risk factors", secondaryMeta: "6 signals", secondaryLines: [["Critical rule", "+30"], ["Protected process access", "+24"], ["SAM export", "+18"], ["New external IP", "+12"], ["Service credential", "+8"], ["No allowlist match", "+6"]],
    bottomTitle: "Response guidance", guidance: ["Validate endpoint owner and business criticality.", "Create an incident and attach source events.", "Isolate the endpoint after confirmation."], related: ["1 endpoint · FIN-LT-042", "2 identities · alice.kim, svc-finance", "14 source events", "3 related alerts"]
  }, 0, gapY);
  buildListScreen(page, {
    title: "Incidents", route: "/incidents", active: "Incidents", subtitle: "Track coordinated investigations and containment progress.",
    filters: ["Last 7 days", "Priority · All", "Status · Active", "Search incidents"],
    summaryToneLabel: "27 ACTIVE", summaryTone: "warning", summary: "4 priority-one · 9 awaiting containment · 6 awaiting owner", total: "27",
    headers: ["PRIORITY", "STATUS", "INCIDENT", "OWNER", "ALERTS", "UPDATED"],
    rows: [
      ["P1", "active", "Finance workstation compromise", "SOC Tier 2", "8", "4m"],
      ["P1", "contained", "Privileged account abuse", "J. Park", "12", "17m"],
      ["P2", "active", "Engineering C2 investigation", "S. Kim", "5", "24m"],
      ["P2", "monitoring", "Unsigned driver campaign", "A. Lee", "9", "41m"],
      ["P3", "closed", "Rare DNS false positive cluster", "SOC Tier 1", "16", "1h"]
    ],
    widths: [140, 180, 420, 220, 150, 228]
  }, gapX, gapY);
  buildDetailScreen(page, {
    title: "Incident Detail", route: "/incidents/:incidentId", active: "Incidents", subtitle: "Scope, timeline, hypotheses, and containment status.",
    status: "ACTIVE · P1", tone: "danger", id: "INC-2026-0713-0042 · Finance workstation compromise", action: "Update status",
    metrics: [["Alerts", "8", "color/status/danger"], ["Endpoints", "3", "color/status/warning"], ["Identities", "4", "color/status/warning"], ["Tactics", "5", "color/status/info"], ["Owner", "Tier 2", "color/status/accent"], ["Age", "2h 18m", "color/text/primary"]],
    primaryTitle: "Incident summary", primaryMeta: "created from alert", primaryLines: [["Priority", "P1 · Critical"], ["Owner", "SOC Tier 2"], ["Status", "Active investigation"], ["Scope", "Finance business unit"], ["Entry point", "Malicious document"], ["Containment", "1 of 3 endpoints"]],
    secondaryTitle: "Activity timeline", secondaryMeta: "latest first", secondaryLines: [["14:48", "Analyst expanded identity scope"], ["14:42", "C2 beacon detected"], ["14:41", "Credential access confirmed"], ["14:36", "PowerShell second stage"], ["14:31", "Initial document execution"], ["14:29", "Email delivered"]],
    bottomTitle: "Next actions", guidance: ["Isolate remaining affected endpoints.", "Rotate svc-finance credentials.", "Collect memory image before remediation."], related: ["8 alerts", "3 endpoints", "4 identities", "21 evidence items"]
  }, gapX * 2, gapY);
  buildListScreen(page, {
    title: "Endpoints", route: "/endpoints", active: "Endpoints", subtitle: "Monitor endpoint posture, sensor health, and response state.",
    filters: ["All business units", "Risk · All", "Sensor · All", "Search hostname"],
    summaryToneLabel: "43 AT RISK", summaryTone: "warning", summary: "2,460 endpoints · 4 isolated · 43 offline", total: "2,460",
    headers: ["RISK", "HOSTNAME", "USER", "OS", "SENSOR", "LAST SEEN"],
    rows: [
      ["CRITICAL", "FIN-LT-042", "alice.kim", "Windows 11", "healthy", "12s"],
      ["HIGH", "HR-WS-118", "min.ji", "Windows 10", "degraded", "2m"],
      ["HIGH", "ENG-LT-077", "dev.park", "Ubuntu 24.04", "healthy", "41s"],
      ["MEDIUM", "OPS-WS-204", "ops.lee", "Windows 11", "healthy", "1m"],
      ["LOW", "MKT-LT-016", "mkt.choi", "macOS 15", "offline", "4h"]
    ],
    widths: [150, 220, 220, 230, 200, 318]
  }, 0, gapY * 2);
  buildDetailScreen(page, {
    title: "Endpoint Detail", route: "/endpoints/:endpointId", active: "Endpoints", subtitle: "Host posture, process signals, network context, and response actions.",
    status: "AT RISK", tone: "danger", id: "FIN-LT-042 · Windows 11 · Finance", action: "Isolate endpoint",
    metrics: [["Risk", "92", "color/status/danger"], ["Alerts", "6", "color/status/danger"], ["Sensor", "Healthy", "color/status/success"], ["Last seen", "12s", "color/status/info"], ["Processes", "184", "color/text/primary"], ["Connections", "31", "color/status/accent"]],
    primaryTitle: "Host profile", primaryMeta: "sensor edr-2.8.1", primaryLines: [["Hostname", "FIN-LT-042"], ["User", "alice.kim"], ["OS", "Windows 11 24H2"], ["IP", "10.24.18.42"], ["Business unit", "Finance"], ["Isolation", "Not isolated"]],
    secondaryTitle: "Recent signals", secondaryMeta: "last 15 min", secondaryLines: [["14:42", "Outbound to 185.220.101.4"], ["14:41", "SAM export created"], ["14:41", "LSASS protected access"], ["14:36", "Encoded PowerShell"], ["14:31", "Word child process"], ["14:29", "Document downloaded"]],
    bottomTitle: "Response guidance", guidance: ["Confirm the endpoint owner and active session.", "Collect triage package for evidence preservation.", "Use typed confirmation before network isolation."], related: ["6 alerts", "1 active incident", "4 identities", "31 network connections"]
  }, gapX, gapY * 2);
  buildListScreen(page, {
    title: "Events", route: "/events", active: "Events", subtitle: "Explore normalized endpoint and network telemetry.",
    filters: ["Last 15 minutes", "Event type · All", "Endpoint · All", "Search raw fields"],
    summaryToneLabel: "6.2K / MIN", summaryTone: "info", summary: "3.8M events retained in active scope · latency p95 1.4 sec", total: "3,842,105",
    headers: ["TIME", "TYPE", "ENDPOINT", "SUMMARY", "SEVERITY", "SOURCE"],
    rows: [
      ["14:42:11.204", "network", "FIN-LT-042", "TLS connection to 185.220.101.4", "high", "sensor"],
      ["14:41:12.188", "file", "FIN-LT-042", "C:\\Temp\\sam.save created", "critical", "sensor"],
      ["14:41:05.084", "process", "FIN-LT-042", "rundll32 accessed lsass", "critical", "sensor"],
      ["14:36:43.991", "process", "FIN-LT-042", "PowerShell encoded command", "high", "sensor"],
      ["14:31:16.403", "process", "FIN-LT-042", "winword spawned powershell", "high", "sensor"]
    ],
    widths: [190, 140, 190, 460, 150, 208]
  }, gapX * 2, gapY * 2);
  buildDetailScreen(page, {
    title: "Event Detail", route: "/events/:eventId", active: "Events", subtitle: "Normalized fields, source event, and linked detections.",
    status: "PROCESS", tone: "info", id: "EVT-2026-0713-884201 · 14:41:05.084", action: "Create alert",
    metrics: [["Severity", "Critical", "color/status/danger"], ["Endpoint", "1", "color/status/info"], ["PID", "4688", "color/text/primary"], ["Rule hits", "3", "color/status/warning"], ["Latency", "1.1s", "color/status/success"], ["Schema", "v3", "color/status/accent"]],
    primaryTitle: "Normalized fields", primaryMeta: "event.process", primaryLines: [["event.type", "process_access"], ["host.name", "FIN-LT-042"], ["user.name", "alice.kim"], ["process.name", "rundll32.exe"], ["target.name", "lsass.exe"], ["access.mask", "0x1FFFFF"]],
    secondaryTitle: "Source event", secondaryMeta: "immutable", secondaryLines: [["provider", "Microsoft-Windows-Sysmon"], ["event_id", "10"], ["sensor", "edr-2.8.1"], ["received_at", "2026-07-13T14:41:06Z"], ["raw_size", "2.4 KB"], ["integrity", "sha256 verified"]],
    bottomTitle: "Detection context", guidance: ["Review parent and child process lineage.", "Check whether access mask matches an allowlisted tool.", "Link to an existing incident when scope overlaps."], related: ["3 rule hits", "2 alerts", "1 endpoint", "4 adjacent events"]
  }, 0, gapY * 3);
  buildOperations(page, gapX, gapY * 3);
  buildArchive(page, gapX * 2, gapY * 3);
  stateBoard(page, 0, gapY * 4);
  responsiveBoard(page, gapX, gapY * 4);
  inventoryBoard(page, gapX * 2, gapY * 4);
  futureTriage(page, 0, gapY * 5);
  futureTimeline(page, gapX, gapY * 5);
  futureEndpoint(page, gapX * 2, gapY * 5);
  futureFailure(page, 0, gapY * 6);
}

async function main() {
  await Promise.all([
    figma.loadFontAsync({ family: "Inter", style: "Regular" }),
    figma.loadFontAsync({ family: "Inter", style: "Medium" }),
    figma.loadFontAsync({ family: "Inter", style: "Semi Bold" }),
    figma.loadFontAsync({ family: "Inter", style: "Bold" }),
    figma.loadFontAsync({ family: "Inter", style: "Extra Bold" }),
    figma.loadFontAsync({ family: "Inter", style: "Black" })
  ]);
  const colors = await figma.variables.getLocalVariablesAsync("COLOR");
  colors.forEach(function(v) { colorVars[v.name] = v; });
  const floats = await figma.variables.getLocalVariablesAsync("FLOAT");
  floats.forEach(function(v) { floatVars[v.name] = v; });

  let coverPage = figma.root.children.find(function(p) { return p.name === "00 · Cover + Foundations"; });
  let libraryPage = figma.root.children.find(function(p) { return p.name === "01 · Component Library"; });
  let productPage = figma.root.children.find(function(p) { return p.name === "02 · Product UX"; });
  if (!coverPage || !libraryPage || !productPage) throw new Error("Expected the three EDR_C pages created during setup.");

  await Promise.all([coverPage.loadAsync(), libraryPage.loadAsync(), productPage.loadAsync()]);
  [coverPage, libraryPage, productPage].forEach(cleanupPage);

  await figma.setCurrentPageAsync(coverPage);
  const foundations = buildCoverAndFoundations(coverPage);

  await figma.setCurrentPageAsync(libraryPage);
  const library = buildLibrary(libraryPage);

  await figma.setCurrentPageAsync(productPage);
  buildProductUX(productPage);

  figma.currentPage.selection = [productPage.children.find(function(n) { return n.name === "Overview / Board"; })].filter(Boolean);
  if (figma.currentPage.selection.length) figma.viewport.scrollAndZoomIntoView(figma.currentPage.selection);
  figma.notify("EDR_C UX library and wireframes created: 3 documentation pages, 12 current routes, states, responsive, and 4 future workflows.", { timeout: 6000 });
  figma.closePlugin();
}

main().catch(function(error) {
  figma.notify("EDR_C UX Builder failed: " + error.message, { error: true, timeout: 10000 });
  console.error(error);
  figma.closePlugin();
});
