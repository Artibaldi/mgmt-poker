// Ядро комнаты: node --test tests/
const test = require("node:test");
const assert = require("node:assert");
const C = require("../poker/web/core.js");

let seq = 0;
const ev = (role, type, data = {}) => ({ seq: ++seq, ts: new Date(Date.UTC(2026, 9, 1, 10, 0, seq)).toISOString(), role, type, data });
const commit = (role, card, vote, why, salt) => ev(role, "commit", { card, hash: C.commitment(card, role, vote, why, salt) });

const deck = {
  meta: { person: "Алексей", period: "сентябрь 2026", role_title: "Тимлид", suits: { "♠": "Хард", "♦": "Софт" } },
  cards: [
    { id: 1, suit: "♠", title: "Техническое лидерство", question: "Насколько?", fact: "", data_view: "данных нет" },
    { id: 2, suit: "♦", title: "Хендофф", question: "Насколько?", fact: "Факт", source: "PAY-1", data_view: "сильная сторона" },
  ],
};

test("sha256 matches node crypto", () => {
  const h = require("crypto").createHash("sha256").update("Привет").digest("hex");
  assert.strictEqual(C.hex(C.sha256(C.utf8("Привет"))), h);
});

test("full card flow: blind commit, verified reveal, co-signed agreement", () => {
  seq = 0;
  const log = [
    ev("host", "hello", { name: "Ирина", half: "a" }), ev("guest", "hello", { name: "Алексей", half: "b" }),
    ev("host", "ready"), ev("guest", "ready"), ev("host", "rec"),
    commit("host", 1, 5, "видел", "s1"),
  ];
  let S = C.reduce(log);
  assert.strictEqual(S.phase, "play");
  assert.ok(S.unsealedAt);
  assert.strictEqual(S.cards[1].reveals.host, undefined);
  // раскрытие до второй печати игнорируется
  log.push(ev("host", "reveal", { card: 1, vote: 5, why: "видел", salt: "s1" }));
  assert.strictEqual(C.reduce(log).cards[1].reveals.host, undefined);
  log.push(commit("guest", 1, 3, "разово", "s2"),
    ev("host", "reveal", { card: 1, vote: 5, why: "видел", salt: "s1" }),
    ev("guest", "reveal", { card: 1, vote: 3, why: "разово", salt: "s2" }));
  S = C.reduce(log);
  assert.ok(S.cards[1].revealedAt);
  assert.ok(S.cards[1].reveals.host.ok && S.cards[1].reveals.guest.ok);
  assert.strictEqual(C.delta(5, 3).kind, "near");
  log.push(ev("host", "draft", { card: 1, text: "Разбор ревью", owner: "Алексей", due: "октябрь" }));
  const d = log[log.length - 1].seq;
  log.push(ev("host", "agree", { card: 1, draft: d }));
  assert.strictEqual(C.cardDone(C.reduce(log).cards[1]), false);
  log.push(ev("guest", "agree", { card: 1, draft: d }));
  S = C.reduce(log);
  assert.strictEqual(C.cardDone(S.cards[1]), true);
  const md = C.toMarkdown(deck, S);
  assert.match(md, /\| Ирина \| 5 \| видел \|/);
  assert.match(md, /\| Алексей \| 3 \| разово \|/);
  assert.match(md, /Разбор ревью — Алексей, срок: октябрь/);
});

test("a new draft resets agreement; tampered reveal is flagged", () => {
  seq = 0;
  const log = [commit("host", 2, 8, "", "x"), commit("guest", 2, 2, "", "y"),
    ev("host", "reveal", { card: 2, vote: 5, why: "", salt: "x" }), ev("guest", "reveal", { card: 2, vote: 2, why: "", salt: "y" }),
    ev("host", "draft", { card: 2, text: "A" })];
  log.push(ev("guest", "agree", { card: 2, draft: log[4].seq }), ev("guest", "draft", { card: 2, text: "B" }));
  const S = C.reduce(log);
  assert.strictEqual(S.cards[2].reveals.host.ok, false);
  assert.deepStrictEqual(S.cards[2].agreed, {});
});

test("only host navigates and closes after both confirmations", () => {
  seq = 0;
  const log = [ev("guest", "nav", { card: 1 }), ev("host", "nav", { card: "summary" }), ev("host", "close")];
  let S = C.reduce(log);
  assert.strictEqual(S.cur, 0);
  assert.strictEqual(S.phase, "summary");
  log.push(ev("host", "summary_ok"), ev("guest", "summary_ok"), ev("host", "close"));
  assert.strictEqual(C.reduce(log).phase, "closed");
});
