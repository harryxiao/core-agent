import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  actionTitle,
  fmtMs,
  labeledTitle,
  stepSymbol,
  thinkingTitle,
  titleFromAction,
  toolName,
  toolTarget,
} from "./activity.js";

describe("toolName", () => {
  it("maps known tool_id", () => {
    assert.equal(toolName("tools.file_read"), "Read");
    assert.equal(toolName("tools.code_run"), "Bash");
  });
  it("strips tools. for unknowns", () => {
    assert.equal(toolName("tools.custom"), "custom");
  });
});

describe("toolTarget", () => {
  it("takes path / first line of script", () => {
    assert.equal(toolTarget("tools.file_read", { path: "src/a.py" }), "src/a.py");
    assert.equal(toolTarget("tools.code_run", { script: "echo hi\nmore" }), "echo hi");
  });
  it("returns empty when missing", () => {
    assert.equal(toolTarget("tools.file_read", {}), "");
    assert.equal(toolTarget("tools.file_read", "legacy-str"), "");
  });
});

describe("actionTitle", () => {
  it("uses paren form without ⏺", () => {
    assert.equal(actionTitle("Read", "src/a.py"), "Read(src/a.py)");
    assert.equal(actionTitle("Bash", ""), "Bash()");
    assert.ok(!actionTitle("Bash", "x").includes("⏺"));
  });
  it("appends completion suffix", () => {
    assert.equal(actionTitle("Read", "a", { ok: true, ms: 12 }), "Read(a) · 12ms");
    assert.equal(actionTitle("Bash", "", { ok: true, ms: 1500 }), "Bash() · 1.5s");
    assert.equal(actionTitle("Read", "a", { ok: false }), "Read(a) · failed");
  });
});

describe("titleFromAction", () => {
  it("composes from tool_id + args", () => {
    assert.equal(
      titleFromAction("tools.file_read", { path: "D:/x.py" }, { ok: true, ms: 31 }),
      "Read(D:/x.py) · 31ms",
    );
  });
});

describe("thinkingTitle", () => {
  it("never embeds content; settle may append duration", () => {
    assert.equal(thinkingTitle(true), "Thinking…");
    assert.equal(thinkingTitle(false), "Thinking");
    assert.equal(thinkingTitle(false, 12), "Thinking · 12ms");
    assert.equal(thinkingTitle(false, 1500), "Thinking · 1.5s");
  });
});

describe("stepSymbol / labeledTitle", () => {
  it("uses distinct icons per kind", () => {
    assert.equal(stepSymbol("Thinking"), "✦");
    assert.equal(stepSymbol("Bash"), "$");
    assert.equal(stepSymbol("WebFetch"), "◎");
    assert.notEqual(stepSymbol("Thinking"), stepSymbol("Bash"));
    assert.equal(labeledTitle("Thinking", "Thinking · 12ms"), "✦ Thinking · 12ms");
  });
});

describe("fmtMs", () => {
  it("formats bounds", () => {
    assert.equal(fmtMs(12), "12ms");
    assert.equal(fmtMs(1500), "1.5s");
    assert.equal(fmtMs("bad"), "");
  });
});
