/* Memory card: what the model chose to remember at the end of a Chapter Segment,
 * with the change since that Character's previous Memory Update highlighted.
 * Loaded before story.js, which calls renderMemoryCard() for each memory Moment.
 */
'use strict';

/* Word-level diff (longest common subsequence). Returns [{op:'same'|'add'|'del', text}],
 * where text keeps its trailing whitespace so the memory's line breaks survive. */
const MEMORY_DIFF_MAX_CELLS = 2_500_000;
function memoryDiff(before, after) {
  const a = String(before || '').match(/\S+\s*/g) || [], b = String(after || '').match(/\S+\s*/g) || [];
  if (!a.length) return b.length ? [{op: 'add', text: b.join('')}] : [];
  if ((a.length + 1) * (b.length + 1) > MEMORY_DIFF_MAX_CELLS) return memorySentenceDiff(before, after);
  const word = token => token.trim();
  const cols = b.length + 1, table = new Uint32Array((a.length + 1) * cols);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i * cols + j] = word(a[i]) === word(b[j])
        ? table[(i + 1) * cols + j + 1] + 1
        : Math.max(table[(i + 1) * cols + j], table[i * cols + j + 1]);
    }
  }
  const parts = [];
  const push = (op, text) => {
    const last = parts.at(-1);
    if (last && last.op === op) last.text += text; else parts.push({op, text});
  };
  let i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (word(a[i]) === word(b[j])) {push('same', b[j]); i++; j++;}
    else if (table[(i + 1) * cols + j] >= table[i * cols + j + 1]) push('del', a[i++]);
    else push('add', b[j++]);
  }
  while (i < a.length) push('del', a[i++]);
  while (j < b.length) push('add', b[j++]);
  return parts;
}
/* Fallback for very long memories: whole sentences are kept or new. */
function memorySentenceDiff(before, after) {
  const split = text => String(text || '').match(/[^.!?\n]+[.!?]*\s*/g) || [];
  const old = new Set(split(before).map(s => s.trim()));
  const parts = [];
  for (const sentence of split(after)) {
    const op = old.has(sentence.trim()) ? 'same' : 'add';
    const last = parts.at(-1);
    if (last && last.op === op) last.text += sentence; else parts.push({op, text: sentence});
  }
  return parts;
}

const MEMORY_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><circle cx="8" cy="8" r="2"/></svg>';
function renderMemoryCard(item) {
  const parts = memoryDiff(item.previous, item.memory);
  const words = op => parts.filter(p => p.op === op).reduce((n, p) => n + (p.text.match(/\S+/g) || []).length, 0);
  const added = words('add'), removed = words('del');
  const change = item.previous
    ? [added && `+${added}`, removed && `−${removed}`].filter(Boolean).join(' ') || 'unchanged'
    : 'first memory';
  const body = parts.map(part => part.op === 'same' ? esc(part.text)
    : part.op === 'add' ? `<mark class="memory-add">${esc(part.text)}</mark>`
    : `<del class="memory-del">${esc(part.text)}</del>`).join('');
  const who = item.character ? ` · ${esc(item.character)}` : '';
  const size = item.max_chars ? `${niceNum(item.length ?? item.memory.length)} / ${niceNum(item.max_chars)} characters${item.truncated ? ', cut to fit' : ''}` : '';
  return `<details class="story-memory" data-index="${item.index}">
    <summary><span class="story-memory-icon">${MEMORY_ICON}</span><span class="story-memory-label">Memory${who}</span><span class="story-memory-change" title="Words added and removed since the last Memory Update">${esc(change)}</span></summary>
    <div class="story-memory-body"><p>${body || '<em>Nothing remembered.</em>'}</p>${size ? `<small>${esc(size)}</small>` : ''}</div>
  </details>`;
}

/* Unfolding a Memory card plays the interface sound, when sound.js is present. */
document.addEventListener('toggle', event => {
  if (!event.target.matches?.('.story-memory') || !event.target.open) return;
  try {window.uiSound?.play?.('unfold');} catch {}
}, true);
