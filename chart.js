export const signOrder = ['serpent', 'tiger', 'monkey', 'hare', 'dragon', 'dog', 'rat', 'ram', 'horse', 'bird', 'ox', 'boar'];

export function selectedSignPool(count, chosen = signOrder) {
  const unique = [...new Set(chosen.filter(sign => signOrder.includes(sign)))];
  if (unique.length < 3) throw new Error('Choose at least three different signs.');
  return unique.slice(0, Math.max(3, Math.min(5, count)));
}

export function buildChart(count, track = {bpm:100, seed:0}, chosen = signOrder) {
  if (track.customMap) {
    const pool = selectedSignPool(count, chosen);
    return track.customMap.notes.map(note => ({
      time: note.time + (track.imported ? 3 : 0), duration: note.duration,
      lane: note.lane, sign: pool[note.signSlot % pool.length], done: false,
      holdBeats: Math.round(note.duration / (60 / track.bpm)),
    }));
  }
  if (track.imported) return buildImportedChart(count, track, chosen);
  const beat = 60 / track.bpm;
  const pool = selectedSignPool(count, chosen);
  // Keep each sign in a consistent lane; higher levels share lanes.
  // Rotate each round to vary the order while including every selected sign.
  const notes = [];
  let time = beat * 5;
  for (let i = 0; time + beat * 2 < 60; i++) {
    const round = Math.floor(i / pool.length);
    const index = (i % pool.length + round + track.seed) % pool.length;
    const duration = (i + track.seed) % 5 === 3 ? (Math.floor(i / 5) % 2 ? beat * 2 : beat) : 0;
    notes.push({time, duration, lane: index % 4, sign: pool[index], done: false});
    time += duration + beat;
  }
  return notes;
}

export function buildImportedChart(count, track, chosen = signOrder) {
  const pool = selectedSignPool(count, chosen);
  const beats = track.beats;
  const notes = [];
  // Every detected beat gets a tap or is covered by an active hold.
  for (let b = 0, i = 0; b < beats.length; i++) {
    const round = Math.floor(i / pool.length);
    const index = (i % pool.length + round + track.seed) % pool.length;
    const holdBeats = i % 5 === 3 ? (Math.floor(i / 5) % 2 ? 2 : 1) : 0;
    const end = Math.min(b + holdBeats, beats.length - 1);
    const duration = beats[end] - beats[b];
    notes.push({time: beats[b] + 3, duration, holdBeats: duration ? end-b : 0,
      lane: index % 4, sign: pool[index], done: false});
    b = end + 1;
  }
  return notes;
}

export function holdResult(note, now, matching, grace = 0) {
  if (matching) note.lastHeld = now;
  if (now - note.lastHeld > grace + 1e-6) return 'broken';
  return now + 1e-6 >= note.time + note.duration ? 'complete' : 'holding';
}
