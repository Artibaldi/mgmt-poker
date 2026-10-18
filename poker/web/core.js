/* Ядро онлайн-комнаты: SHA-256/HMAC, снятие печати с колоды, печати оценок
 * (commit–reveal), свёртка журнала событий в состояние, выгрузка итогов.
 * Работает в браузере (window.PokerCore) и в Node (module.exports) — для тестов.
 * Совместимо с poker/seal.py. */
(function (root) {
  "use strict";

  // ---------- SHA-256 / HMAC (без WebCrypto: работает и по http через VPN) ----------
  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]);

  function sha256(data) {
    const len = data.length, bitLen = len * 8;
    const total = ((len + 9 + 63) >> 6) << 6;
    const m = new Uint8Array(total);
    m.set(data); m[len] = 0x80;
    const dv = new DataView(m.buffer);
    dv.setUint32(total - 8, Math.floor(bitLen / 0x100000000)); dv.setUint32(total - 4, bitLen >>> 0);
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const W = new Uint32Array(64);
    const rotr = (x, n) => (x >>> n) | (x << (32 - n));
    for (let off = 0; off < total; off += 64) {
      for (let i = 0; i < 16; i++) W[i] = dv.getUint32(off + i * 4);
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >>> 3);
        const s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + W[i]) >>> 0;
        const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    const out = new Uint8Array(32), odv = new DataView(out.buffer);
    for (let i = 0; i < 8; i++) odv.setUint32(i * 4, H[i]);
    return out;
  }

  function concat(...parts) {
    const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
    let o = 0; for (const p of parts) { out.set(p, o); o += p.length; }
    return out;
  }

  function hmac(key, msg) {
    if (key.length > 64) key = sha256(key);
    const k = new Uint8Array(64); k.set(key);
    const ipad = k.map((x) => x ^ 0x36), opad = k.map((x) => x ^ 0x5c);
    return sha256(concat(opad, sha256(concat(ipad, msg))));
  }

  const utf8 = (s) => new TextEncoder().encode(s);
  const hex = (b) => Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  const xor = (a, b) => a.map((x, i) => x ^ b[i]);
  function b64u(s) {
    const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4));
    return Uint8Array.from(bin, (c) => c.charCodeAt(0));
  }

  // ---------- печать колоды ----------
  function keyFromHalves(h1, h2) { return xor(b64u(h1), b64u(h2)); }

  function unseal(blob, key) {
    if (blob.alg !== "sha256-ctr+hmac-sha256") throw new Error("неизвестная печать");
    const enc = hmac(key, utf8("enc")), mac = hmac(key, utf8("mac"));
    const nonce = b64u(blob.nonce), ct = b64u(blob.ct);
    if (hex(hmac(mac, concat(nonce, ct))) !== hex(b64u(blob.tag))) throw new Error("печать повреждена или ключ неверный");
    const ks = new Uint8Array(ct.length);
    for (let i = 0, o = 0; o < ct.length; i++, o += 32) {
      const ctr = new Uint8Array(4); new DataView(ctr.buffer).setUint32(0, i);
      ks.set(sha256(concat(enc, nonce, ctr)).subarray(0, Math.min(32, ct.length - o)), o);
    }
    return JSON.parse(new TextDecoder().decode(xor(ct, ks)));
  }

  // ---------- печати оценок (commit–reveal) ----------
  function commitment(card, role, vote, why, salt) {
    return hex(sha256(utf8(`${card}|${role}|${vote}|${salt}|${why}`)));
  }
  function newSalt() {
    const b = new Uint8Array(16); (root.crypto || require("crypto").webcrypto).getRandomValues(b); return hex(b);
  }

  // ---------- шкала ----------
  const STEPS = [1, 2, 3, 5, 8];
  function delta(a, b) {
    if (a == null || b == null) return null;
    if (a === "?" || b === "?") return { kind: "gap", n: null, text: "Есть «?» — нужен разговор" };
    const n = Math.abs(STEPS.indexOf(a) - STEPS.indexOf(b));
    if (n === 0) return { kind: "same", n, text: "Сошлись" };
    if (n === 1) return { kind: "near", n, text: "Близко — расхождение на шаг" };
    return { kind: "gap", n, text: `Разрыв на ${n} шага — обсудить` };
  }

  // ---------- журнал событий → состояние ----------
  const ROLES = ["host", "guest"];
  function emptyCard() {
    return { read: {}, flag: null, commits: {}, reveals: {}, revealedAt: null, drafts: [], agreed: {}, dropped: false };
  }

  function reduce(events) {
    const S = { players: { host: {}, guest: {} }, phase: "lobby", cur: 0, rec: null, pause: null, back: null,
                cards: {}, summaryOk: {}, unsealedAt: null, startedAt: null, closedAt: null };
    const card = (id) => (S.cards[id] = S.cards[id] || emptyCard());
    for (const e of events) {
      const d = e.data || {}, r = e.role;
      switch (e.type) {
        case "hello":
          S.players[r] = Object.assign({}, S.players[r], { name: d.name, half: d.half, joinedAt: S.players[r].joinedAt || e.ts });
          if (!S.unsealedAt && S.players.host.half && S.players.guest.half) S.unsealedAt = e.ts;
          break;
        case "ready":
          S.players[r].ready = true;
          if (S.phase === "lobby" && S.players.host.ready && S.players.guest.ready) { S.phase = "play"; S.startedAt = e.ts; }
          break;
        case "rec": if (r === "host") S.rec = e.ts; break;
        case "nav":
          if (r !== "host" || S.phase === "closed") break;
          if (d.card === "summary") S.phase = "summary";
          else { S.cur = d.card; if (S.phase === "summary") S.phase = "play"; }
          S.pause = null; S.back = null;
          break;
        case "read": { const c = card(d.card); c.read[r] = true; if (d.flag) c.flag = { role: r, text: d.text || "" }; break; }
        case "drop": if (r === "host") card(d.card).dropped = true; break;
        case "commit": { const c = card(d.card); if (!c.commits[r]) c.commits[r] = d.hash; break; }
        case "reveal": {
          const c = card(d.card);
          if (!c.commits.host || !c.commits.guest || c.reveals[r]) break;
          const ok = commitment(d.card, r, d.vote, d.why || "", d.salt) === c.commits[r];
          c.reveals[r] = { vote: d.vote, why: d.why || "", ok };
          if (c.reveals.host && c.reveals.guest) c.revealedAt = e.ts;
          break;
        }
        case "draft": { const c = card(d.card); c.drafts.push({ seq: e.seq, role: r, text: d.text || "", owner: d.owner || "", due: d.due || "" }); c.agreed = {}; break; }
        case "agree": { const c = card(d.card); const last = c.drafts[c.drafts.length - 1]; if (last && last.seq === d.draft) c.agreed[r] = true; break; }
        case "pause": S.pause = d.on ? { role: r, ts: e.ts } : null; break;
        case "back": S.back = { card: d.card, ts: e.ts }; break;
        case "summary_ok": S.summaryOk[r] = true; break;
        case "close": if (r === "host" && S.summaryOk.host && S.summaryOk.guest) { S.phase = "closed"; S.closedAt = e.ts; } break;
      }
    }
    return S;
  }

  function cardDone(c) {
    if (!c) return false;
    if (c.dropped) return true;
    return !!(c.revealedAt && c.drafts.length && c.agreed.host && c.agreed.guest);
  }
  function agreement(c) { return c && c.agreed.host && c.agreed.guest ? c.drafts[c.drafts.length - 1] : null; }
  function timecode(S, ts) {
    if (!S.rec || !ts) return "";
    const s = Math.max(0, Math.round((Date.parse(ts) - Date.parse(S.rec)) / 1000));
    const p = (n) => String(n).padStart(2, "0");
    return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
  }

  // ---------- итоги ----------
  function suitStats(deck, S) {
    const out = {};
    for (const c of deck.cards) {
      const st = S.cards[c.id], v = st && st.revealedAt && !st.dropped ? st.reveals : null;
      const o = (out[c.suit] = out[c.suit] || { n: 0, host: [], guest: [] });
      if (!v) continue;
      o.n++;
      for (const r of ROLES) if (typeof v[r].vote === "number") o[r].push(v[r].vote);
    }
    const avg = (xs) => (xs.length ? (xs.reduce((a, b) => a + b, 0) / xs.length).toFixed(1) : "—");
    return Object.keys(out).map((s) => ({ suit: s, name: (deck.meta.suits || {})[s] || s, n: out[s].n, host: avg(out[s].host), guest: avg(out[s].guest) }));
  }

  function toMarkdown(deck, S) {
    const M = deck.meta, P = { host: S.players.host.name || "Руководитель", guest: S.players.guest.name || M.person };
    const cell = (s) => String(s == null ? "" : s).replace(/\|/g, "\\|").replace(/\n+/g, " ");
    const L = [
      `# Итоги управленческого покера — ${M.person}, ${M.period}`, "",
      `- Роль: ${M.role_title || M.role || "—"}`,
      `- Игроки: ${P.host} (руководитель), ${P.guest} (сотрудник)`,
      `- Колода вскрыта: ${S.unsealedAt || "—"}; встреча закрыта: ${S.closedAt || "—"}`,
      S.rec ? `- Запись ВКС с ${S.rec}; таймкоды ниже — от начала записи` : "- Таймкоды: запись не отмечена", "",
      "## Сводка по мастям", "", `| Масть | Карт | ${P.host} | ${P.guest} |`, "|---|---|---|---|",
      ...suitStats(deck, S).map((x) => `| ${x.suit} ${x.name} | ${x.n} | ${x.host} | ${x.guest} |`), "",
      "## Договорённости", "",
    ];
    const agr = deck.cards.map((c) => [c, agreement(S.cards[c.id])]).filter(([, a]) => a);
    L.push(...(agr.length ? agr.map(([c, a]) => `- **${c.suit} ${c.title}:** ${a.text}${a.owner ? ` — ${a.owner}` : ""}${a.due ? `, срок: ${a.due}` : ""}`) : ["_нет_"]), "", "## Карты", "");
    deck.cards.forEach((c, i) => {
      const st = S.cards[c.id] || emptyCard(), v = st.reveals, d = st.revealedAt ? delta(v.host.vote, v.guest.vote) : null, a = agreement(st);
      L.push(`### ${i + 1}. ${c.suit} ${c.title}${st.dropped ? " — снята" : ""}`, "");
      if (c.fact) L.push(c.fact, "");
      L.push(`**Вопрос:** ${c.question}`);
      if (c.source) L.push(`**Источник:** ${c.source}`);
      if (st.flag) L.push(`**Факт оспорен** (${P[st.flag.role]}): ${st.flag.text || "без комментария"}`);
      if (st.revealedAt) {
        L.push("", `| | Оценка | Почему |`, "|---|---|---|",
          `| ${P.host} | ${v.host.vote}${v.host.ok ? "" : " ⚠️"} | ${cell(v.host.why)} |`,
          `| ${P.guest} | ${v.guest.vote}${v.guest.ok ? "" : " ⚠️"} | ${cell(v.guest.why)} |`, "",
          `**Разница:** ${d.text}${timecode(S, st.revealedAt) ? ` · таймкод ${timecode(S, st.revealedAt)}` : ""}`);
        if (c.data_view) L.push(`**Что показывают данные:** ${c.data_view}`);
      } else if (!st.dropped) L.push("", "_не сыграна_");
      if (a) L.push(`**Договорённость:** ${a.text}${a.owner ? ` — ${a.owner}` : ""}${a.due ? `, срок: ${a.due}` : ""}`);
      L.push("");
    });
    L.push("⚠️ — оценка не совпала со своей печатью (не должно происходить; сообщите руководителю).");
    return L.join("\n");
  }

  const api = { sha256, hmac, hex, utf8, b64u, keyFromHalves, unseal, commitment, newSalt, STEPS, delta,
                reduce, cardDone, agreement, timecode, suitStats, toMarkdown };
  root.PokerCore = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
